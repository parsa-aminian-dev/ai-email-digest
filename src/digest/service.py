from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.digest.config.settings import Settings
from src.digest.demo import demo_emails
from src.digest.digest.builder import DigestBuilder
from src.digest.digest.delivery import Delivery
from src.digest.llm.base import LLMAdapter, MockLLMAdapter
from src.digest.llm.openai import OpenAIAdapter
from src.digest.logging import event
from src.digest.models import DigestResult, EmailMessage
from src.digest.pipeline.processor import EmailProcessor
from src.digest.pipeline.schedule import daily_window
from src.digest.providers.base import DemoProvider, MailProvider
from src.digest.providers.gmail import GmailProvider
from src.digest.storage.repository import EmailRepository


class DigestService:
    def __init__(
        self,
        settings: Settings | None = None,
        repository: EmailRepository | None = None,
        provider: MailProvider | None = None,
        *,
        initialize_integrations: bool = True,
    ) -> None:
        self.settings = settings or Settings()
        self.config = self.settings.rules
        self.repository = repository or EmailRepository(self.settings.database_path)
        adapter: LLMAdapter | None = None
        if initialize_integrations and self.config.llm.provider == "mock":
            if not self.settings.demo_mode:
                raise ValueError("Mock AI is allowed only in demo mode")
            adapter = MockLLMAdapter()
        elif initialize_integrations and self.config.llm.provider == "openai":
            adapter = OpenAIAdapter(self.settings, self.config, self.repository)
        self.processor = EmailProcessor(adapter, self.config, self.settings)
        self.builder = DigestBuilder(self.config)
        self.delivery = Delivery(self.settings)
        self.provider = provider or (
            DemoProvider(demo_emails())
            if self.settings.demo_mode or not initialize_integrations
            else GmailProvider(self.settings)
        )

    def close(self) -> None:
        if self.processor.llm_adapter:
            self.processor.llm_adapter.close()
        close = getattr(self.provider, "close", None)
        if close:
            close()

    def process_batch(self, messages: Sequence[dict[str, Any] | EmailMessage]) -> dict[str, Any]:
        started = time.monotonic()
        report: dict[str, Any] = {
            "run_id": str(uuid.uuid4()),
            "processed": 0,
            "duplicates": 0,
            "failures": 0,
            "expired": 0,
            "llm_fallbacks": 0,
            "llm_calls": 0,
            "llm_tokens": 0,
        }
        items = []
        adapter = self.processor.llm_adapter
        calls, tokens = (adapter.calls, adapter.tokens) if adapter else (0, 0)
        cutoff = datetime.now(UTC) - timedelta(days=self.config.retention_days)
        with self.repository.lease("processing"):
            for raw in messages:
                try:
                    email = (
                        raw if isinstance(raw, EmailMessage) else EmailMessage.model_validate(raw)
                    )
                    if email.received_at < cutoff:
                        report["expired"] += 1
                        continue
                    existing = self.repository.get(email.id)
                    if existing:
                        report["duplicates"] += 1
                        items.append(existing)
                        continue
                    item = self.processor.process(email)
                    if self.repository.save(item):
                        report["processed"] += 1
                        report["llm_fallbacks"] += int(item.llm_fallback)
                    else:
                        report["duplicates"] += 1
                    items.append(item)
                except Exception as error:
                    report["failures"] += 1
                    event("email_failed", run_id=report["run_id"], error_class=type(error).__name__)
            if adapter:
                report["llm_calls"], report["llm_tokens"] = (
                    adapter.calls - calls,
                    adapter.tokens - tokens,
                )
            report["duration_seconds"] = round(time.monotonic() - started, 3)
            self.repository.record_run(report)
            self.repository.cleanup(self.config.retention_days)
        event("batch_complete", **report)
        return {
            "items": [item.model_dump(mode="json") for item in items],
            "report": report,
            "digest": self.builder.build(items, report).model_dump(mode="json"),
        }

    def ingest(self) -> dict[str, Any]:
        with self.repository.lease("ingestion"):
            started = datetime.now(UTC)
            saved = self.repository.get_state("gmail_checkpoint")
            since = (
                datetime.fromisoformat(saved) - timedelta(hours=1)
                if saved
                else started - timedelta(days=self.config.retention_days)
            )
            try:
                if self.settings.demo_mode and isinstance(self.provider, DemoProvider):
                    self.provider = DemoProvider(demo_emails(started))
                messages = self.provider.fetch_messages(since)
                result = self.process_batch(messages)
                failures = self.provider.failures
                result["report"]["provider_failures"] = failures
                if failures:
                    self.repository.record_run({"provider_failures": failures})
                if not failures and not result["report"]["failures"]:
                    self.repository.set_state("gmail_checkpoint", started.isoformat())
                return result["report"]
            except Exception as error:
                report = {
                    "run_id": str(uuid.uuid4()),
                    "processed": 0,
                    "failures": 0,
                    "provider_failures": 1,
                }
                self.repository.record_run(report)
                event("ingestion_failed", **report, error_class=type(error).__name__)
                return report

    def generate_digest(
        self, start: datetime | None = None, end: datetime | None = None, *, deliver: bool = False
    ) -> DigestResult:
        now = datetime.now(UTC)
        if (start is None) != (end is None):
            raise ValueError("Provide both start and end, or neither")
        if start is None or end is None:
            start, end = daily_window(now, self.config.digest)
        start, end = start.astimezone(UTC), end.astimezone(UTC)
        if (
            start >= end
            or (end - start) > timedelta(days=self.config.retention_days)
            or end <= now - timedelta(days=self.config.retention_days)
        ):
            raise ValueError("Invalid digest period")
        digest_id = hashlib.sha256(f"{start.isoformat()}|{end.isoformat()}".encode()).hexdigest()[
            :32
        ]
        with self.repository.lease("digest_generation"):
            result = self.repository.get_digest(digest_id)
            if result is None:
                items = self.repository.list_period(start, end)
                health = self.repository.run_health(start, max(now, end))
                result = self.builder.build(items, health)
                result.id, result.interval_start, result.interval_end = digest_id, start, end
                adapter = self.processor.llm_adapter
                if adapter and self.config.llm.overall_summary and items:
                    calls, tokens = adapter.calls, adapter.tokens
                    try:
                        result.overall_summary = adapter.summarize(
                            {
                                "processed": len(items),
                                "language": self.config.digest.language,
                                "groups": [
                                    {
                                        "category": group.category,
                                        "priority": group.priority,
                                        "count": group.count,
                                        "summaries": [item.summary for item in group.items],
                                    }
                                    for group in result.entries
                                ],
                            }
                        )
                        result.ai_summary_used = True
                    except Exception as error:
                        result.health["overview_fallback"] = 1
                        event("overview_failed", error_class=type(error).__name__)
                    result.health["llm_calls"] = (
                        result.health.get("llm_calls", 0) + adapter.calls - calls
                    )
                    result.health["llm_tokens"] = (
                        result.health.get("llm_tokens", 0) + adapter.tokens - tokens
                    )
                self.builder.render(result)
                self.repository.save_digest(result)
            if deliver:
                self.delivery.validate()  # Configuration errors are safe to retry before claiming.
                if self.repository.claim_delivery(digest_id):
                    try:
                        self.delivery.send(result)
                    except Exception as error:
                        # SMTP can accept a message before losing the connection. Never resend blindly.
                        self.repository.mark_delivery(digest_id, "uncertain")
                        event(
                            "delivery_uncertain",
                            digest_id=digest_id,
                            error_class=type(error).__name__,
                        )
                        raise
                    self.repository.mark_delivery(digest_id, "sent")
        return result

    def run_scheduled(self) -> dict[str, Any]:
        report = self.ingest()
        result = self.generate_digest(deliver=True)
        self.repository.cleanup(self.config.retention_days)
        self.cleanup_previews()
        return {
            "report": report,
            "digest_id": result.id,
            "delivery": self.repository.delivery_state(result.id),
        }

    def cleanup_previews(self) -> None:
        directory = Path(self.settings.output_dir)
        cutoff = (datetime.now(UTC) - timedelta(days=self.config.retention_days)).timestamp()
        if directory.exists():
            for path in directory.iterdir():
                if (
                    path.is_file()
                    and path.suffix in {".html", ".txt"}
                    and path.stat().st_mtime < cutoff
                ):
                    path.unlink()

    def purge(self) -> None:
        self.repository.purge()
        directory = Path(self.settings.output_dir)
        if directory.exists():
            for path in directory.iterdir():
                if path.is_file() and path.suffix in {".html", ".txt"}:
                    path.unlink()
