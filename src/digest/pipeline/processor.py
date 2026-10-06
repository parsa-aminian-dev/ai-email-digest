from __future__ import annotations

import re
from datetime import UTC, datetime

from src.digest.config.settings import RulesConfig, Settings
from src.digest.digest.builder import DigestBuilder as DigestBuilder
from src.digest.llm.base import LLMAdapter
from src.digest.models import PRIORITY_ORDER, Action, AnalysisOutput, EmailMessage, ProcessedEmail
from src.digest.preprocessing.redact import normalize_email_text, safe_text
from src.digest.rules.engine import evaluate_rule_engine


class EmailProcessor:
    def __init__(
        self,
        llm_adapter: LLMAdapter | None = None,
        config: RulesConfig | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.config = config or self.settings.rules
        self.llm_adapter = llm_adapter

    def process(self, email: EmailMessage) -> ProcessedEmail:
        if len(email.body.encode()) > self.settings.max_message_size_bytes:
            # Bytes are bounded before parsing; multibyte text is decoded safely.
            body = email.body.encode()[: self.settings.max_message_size_bytes].decode(
                "utf-8", errors="ignore"
            )
        else:
            body = email.body
        local = email.model_copy(
            update={"body": normalize_email_text(body, self.config.max_body_chars)}
        )
        decision = evaluate_rule_engine(local, self.config)
        relevant = (
            PRIORITY_ORDER[decision.priority]
            <= PRIORITY_ORDER[self.config.digest.summary_threshold]
        )
        needs_ai = (
            decision.llm_required
            or decision.confidence < self.config.llm.confidence_threshold
            or (relevant and not decision.locked)
        )
        used, fallback = False, False
        # An extractive fallback keeps useful details without inventing facts.
        excerpt = " ".join(re.split(r"(?<=[.!?])\s+", local.body)[:2])
        summary = (
            safe_text(excerpt, 350)
            or safe_text(local.subject, 300)
            or "Empty message; review inbox."
        )
        if self.llm_adapter and needs_ai:
            calls_before = self.llm_adapter.calls
            minimal = EmailMessage(
                id="minimized",
                sender=f"redacted@{email.sender_domain}",
                subject=safe_text(local.subject, 300),
                body=safe_text(local.body, self.config.max_body_chars),
                received_at=email.received_at,
            )
            try:
                result = AnalysisOutput.model_validate(self.llm_adapter.analyze(minimal))
                used = True
                if result.category not in {category.name for category in self.config.categories}:
                    raise ValueError("Invalid category")
                source = f"{minimal.subject} {minimal.body}".lower()
                if result.evidence and result.evidence.lower() not in source:
                    raise ValueError("Ungrounded analysis")
                if result.deadline and result.deadline.lower() not in source:
                    raise ValueError("Ungrounded deadline")
                if not result.evidence and (
                    result.action_type != Action.none or result.confidence > 0.5 or result.deadline
                ):
                    raise ValueError("Evidence missing")
                if not decision.locked:
                    decision.category = result.category
                    # AI cannot downgrade a deterministic HIGH/URGENT hint.
                    if (
                        PRIORITY_ORDER[result.priority] < PRIORITY_ORDER[decision.priority]
                        or PRIORITY_ORDER[decision.priority] > 1
                    ):
                        decision.priority = result.priority
                    decision.resolved_by_rules = False
                if decision.action_type == Action.none:
                    decision.action_type = result.action_type
                decision.deadline = decision.deadline or result.deadline
                decision.confidence = result.confidence
                summary = safe_text(result.summary)
            except Exception:
                used = used or self.llm_adapter.calls > calls_before
                fallback = True
        return ProcessedEmail(
            id=email.id,
            received_at=email.received_at,
            processed_at=datetime.now(UTC),
            sender_domain=email.sender_domain,
            subject=safe_text(email.subject, 300),
            category=decision.category,
            priority=decision.priority,
            action_type=decision.action_type,
            deadline=safe_text(decision.deadline, 80) if decision.deadline else None,
            summary=summary if relevant or needs_ai else "",
            confidence=decision.confidence,
            resolved_by_rules=decision.resolved_by_rules,
            llm_used=used,
            llm_fallback=fallback,
            status="needs_review"
            if fallback or not decision.resolved_by_rules and not used
            else "processed",
        )

    @staticmethod
    def parse_model(item: dict[str, object]) -> ProcessedEmail:
        return ProcessedEmail.model_validate(item)
