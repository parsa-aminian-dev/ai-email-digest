from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.digest.models import AnalysisOutput, EmailMessage, Priority
from src.digest.preprocessing.redact import safe_text


class LLMAdapter(ABC):
    calls: int = 0
    tokens: int = 0

    @abstractmethod
    def analyze(self, email: EmailMessage) -> AnalysisOutput:
        raise NotImplementedError

    def summarize(self, payload: dict[str, Any]) -> str:
        raise NotImplementedError

    def close(self) -> None:
        """Release any adapter-owned resources."""
        return None


class MockLLMAdapter(LLMAdapter):
    """Deterministic demonstration adapter; never makes a network request."""

    def analyze(self, email: EmailMessage) -> AnalysisOutput:
        from src.digest.rules.engine import extract_action

        self.calls += 1
        action, deadline = extract_action(f"{email.subject} {email.body}")
        evidence = safe_text(email.body, 120)
        return AnalysisOutput(
            category="general",
            priority=Priority.MEDIUM,
            action_type=action,
            deadline=deadline,
            summary=evidence or "Empty message; review inbox.",
            evidence=evidence,
            confidence=0.6,
        )

    def summarize(self, payload: dict[str, Any]) -> str:
        self.calls += 1
        return f"{payload['processed']} messages reviewed; prioritize the listed actions."
