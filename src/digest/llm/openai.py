from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from src.digest.config.settings import RulesConfig, Settings
from src.digest.llm.base import LLMAdapter
from src.digest.models import AnalysisOutput, EmailMessage
from src.digest.preprocessing.redact import safe_text
from src.digest.storage.repository import EmailRepository


class TokenBudgetExceeded(RuntimeError):
    pass


class OpenAIAdapter(LLMAdapter):
    def __init__(
        self,
        settings: Settings,
        config: RulesConfig,
        repository: EmailRepository,
        client: httpx.Client | None = None,
    ) -> None:
        if not settings.openai_api_key.get_secret_value():
            raise ValueError("OPENAI_API_KEY is required for the openai provider")
        self.settings, self.config, self.repository = settings, config, repository
        self.client = client or httpx.Client(timeout=config.llm.timeout_seconds)
        self._owns_client = client is None
        self.calls = 0
        self.tokens = 0
        self.prompts_path = Path(__file__).resolve().parents[3] / "prompts"

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _complete(
        self, prompt: str, payload: dict[str, Any], schema: dict[str, Any]
    ) -> dict[str, Any]:
        body = {
            "model": self.config.llm.model,
            "store": False,
            "messages": [
                {"role": "system", "content": (self.prompts_path / prompt).read_text()},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "max_completion_tokens": self.config.llm.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "digest_analysis", "strict": True, "schema": schema},
            },
        }
        # A byte-based upper bound plus schema/chat overhead is deliberately conservative.
        reservation = (
            len(json.dumps(body, ensure_ascii=False).encode())
            + self.config.llm.max_output_tokens
            + 1024
        )
        day = datetime.now(UTC).astimezone(ZoneInfo(self.config.digest.timezone)).date().isoformat()
        for attempt in range(3):
            if not self.repository.reserve_tokens(
                day, reservation, self.config.llm.daily_token_budget
            ):
                raise TokenBudgetExceeded("Daily token budget exhausted")
            self.calls += 1
            try:
                response = self.client.post(
                    "https://api.openai.com/v1/chat/completions",
                    json=body,
                    headers={
                        "Authorization": f"Bearer {self.settings.openai_api_key.get_secret_value()}"
                    },
                )
                response.raise_for_status()
                result = response.json()
                self.tokens += int(result.get("usage", {}).get("total_tokens", 0))
                choice = result["choices"][0]
                if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
                    raise ValueError("Model output refused or incomplete")
                output = json.loads(choice["message"]["content"])
                if not isinstance(output, dict):
                    raise ValueError("Expected JSON object")
                return output
            except (httpx.NetworkError, httpx.TimeoutException, httpx.HTTPStatusError) as error:
                retryable = not isinstance(
                    error, httpx.HTTPStatusError
                ) or error.response.status_code in {429, 500, 502, 503, 504}
                if not retryable or attempt == 2:
                    raise
                time.sleep(0.25 * 2**attempt)
        raise RuntimeError("Completion exhausted")

    def analyze(self, email: EmailMessage) -> AnalysisOutput:
        categories = [category.name for category in self.config.categories]
        schema = AnalysisOutput.model_json_schema()
        schema["properties"]["category"]["enum"] = categories
        payload = {
            "sender_domain": email.sender_domain,
            "subject": safe_text(email.subject, 300),
            "body": safe_text(email.body, self.config.max_body_chars),
            "categories": categories,
            "language": self.config.digest.language,
        }
        output = AnalysisOutput.model_validate(self._complete("analyze.txt", payload, schema))
        if output.category not in categories:
            raise ValueError("Unconfigured category")
        source = f"{payload['subject']} {payload['body']}".lower()
        if output.evidence and output.evidence.lower() not in source:
            raise ValueError("Unsupported evidence")
        if not output.evidence and (
            output.action_type != "none" or output.deadline is not None or output.confidence > 0.5
        ):
            raise ValueError("Evidence required")
        if output.deadline and output.deadline.lower() not in source:
            raise ValueError("Unsupported deadline")
        return output

    def summarize(self, payload: dict[str, Any]) -> str:
        schema = {
            "type": "object",
            "properties": {"summary": {"type": "string", "maxLength": 500}},
            "required": ["summary"],
            "additionalProperties": False,
        }
        result = self._complete("overview.txt", payload, schema)
        if (
            set(result) != {"summary"}
            or not isinstance(result["summary"], str)
            or len(result["summary"]) > 500
        ):
            raise ValueError("Invalid overview")
        return safe_text(result["summary"])
