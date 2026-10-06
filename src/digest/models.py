from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parseaddr
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Priority(StrEnum):
    URGENT = "URGENT"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


PRIORITY_ORDER = {priority: index for index, priority in enumerate(Priority)}


class Action(StrEnum):
    reply = "reply"
    confirm = "confirm"
    pay = "pay"
    attend = "attend"
    submit = "submit"
    change = "change"
    contact = "contact"
    none = "none"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class EmailMessage(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    sender: str = Field(max_length=500)
    subject: str = Field(default="", max_length=2000)
    body: str = ""
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    labels: list[str] = Field(default_factory=list, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("received_at")
    @classmethod
    def aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("received_at must include a timezone")
        return value.astimezone(UTC)

    @property
    def sender_domain(self) -> str:
        address = parseaddr(self.sender)[1].lower()
        return address.rsplit("@", 1)[1] if "@" in address else "unknown"


class RuleDecision(StrictModel):
    category: str = Field(min_length=1, max_length=80)
    priority: Priority
    confidence: float = Field(ge=0, le=1)
    action_type: Action = Action.none
    deadline: str | None = Field(default=None, max_length=80)
    summary: str = Field(default="", max_length=500)
    evidence: str = Field(default="", max_length=300)
    resolved_by_rules: bool = True
    llm_required: bool = False
    locked: bool = False


class AnalysisOutput(StrictModel):
    category: str = Field(min_length=1, max_length=80)
    priority: Priority
    action_type: Action
    deadline: str | None = Field(max_length=80)
    summary: str = Field(max_length=500)
    evidence: str = Field(max_length=300)
    confidence: float = Field(ge=0, le=1)


class ProcessedEmail(StrictModel):
    id: str
    received_at: datetime
    processed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sender_domain: str
    subject: str = Field(default="", max_length=300)
    category: str
    priority: Priority
    action_type: Action = Action.none
    deadline: str | None = None
    summary: str = Field(default="", max_length=500)
    confidence: float = 0
    resolved_by_rules: bool = True
    llm_used: bool = False
    llm_fallback: bool = False
    status: str = "processed"


class DigestEntry(StrictModel):
    category: str
    priority: Priority
    count: int = 0
    items: list[ProcessedEmail] = Field(default_factory=list)


class DigestResult(StrictModel):
    id: str = ""
    generated_at: datetime
    interval_start: datetime | None = None
    interval_end: datetime | None = None
    entries: list[DigestEntry] = Field(default_factory=list)
    overall_summary: str = ""
    ai_summary_used: bool = False
    health: dict[str, Any] = Field(default_factory=dict)
    text: str = ""
    html: str = ""


class ProcessBatchRequest(StrictModel):
    # Validate each message separately so a bad message cannot reject the whole batch.
    messages: list[dict[str, Any]] = Field(max_length=500)


class DigestRequest(StrictModel):
    start: datetime | None = None
    end: datetime | None = None
    deliver: bool = False

    @field_validator("start", "end")
    @classmethod
    def aware_window(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Digest dates must include a timezone")
        return value.astimezone(UTC) if value else None
