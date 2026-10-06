from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.digest.models import EmailMessage


class MailProvider(ABC):
    failures: int = 0

    @abstractmethod
    def fetch_messages(self, since: datetime | None = None) -> list[EmailMessage]:
        raise NotImplementedError


class DemoProvider(MailProvider):
    def __init__(self, messages: list[EmailMessage] | None = None) -> None:
        self._messages = messages or []

    def fetch_messages(self, since: datetime | None = None) -> list[EmailMessage]:
        return [
            item.model_copy(deep=True)
            for item in self._messages
            if since is None or item.received_at >= since
        ]
