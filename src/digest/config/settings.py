from __future__ import annotations

import re
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.digest.models import Action, Priority, StrictModel


class CategoryConfig(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,79}$")
    priority: Priority = Priority.MEDIUM
    keywords: list[str] = Field(default_factory=list)


class RuleMatch(StrictModel):
    sender: str | None = None
    sender_domain: str | None = None
    subject_pattern: str | None = None
    body_contains: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    list_unsubscribe: bool | None = None

    @field_validator("subject_pattern")
    @classmethod
    def validate_pattern(cls, value: str | None) -> str | None:
        if value:
            re.compile(value)
        return value


class RuleConfig(StrictModel):
    id: str
    when: RuleMatch
    category: str
    priority: Priority
    action_type: Action = Action.none
    confidence: float = Field(default=1, ge=0, le=1)
    analyze: bool = False


class DigestConfig(StrictModel):
    time: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = "Europe/Berlin"
    language: Literal["en", "de"] = "en"
    summary_threshold: Priority = Priority.MEDIUM
    max_items: int = Field(default=20, ge=1, le=500)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


class LLMConfig(StrictModel):
    provider: Literal["disabled", "mock", "openai"] = "disabled"
    model: str = "gpt-4o-mini"
    daily_token_budget: int = Field(default=20000, ge=0)
    max_output_tokens: int = Field(default=600, ge=100, le=4000)
    timeout_seconds: float = Field(default=30, gt=0, le=120)
    confidence_threshold: float = Field(default=0.85, ge=0, le=1)
    overall_summary: bool = True


class RulesConfig(StrictModel):
    categories: list[CategoryConfig] = Field(min_length=1)
    digest: DigestConfig = Field(default_factory=DigestConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    retention_days: int = Field(default=30, ge=1, le=365)
    max_body_chars: int = Field(default=4000, ge=100, le=20000)
    rules: list[RuleConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_categories(self) -> RulesConfig:
        names = [c.name for c in self.categories]
        if len(set(names)) != len(names) or "general" not in names:
            raise ValueError("Categories must be unique and include general")
        if any(rule.category not in names for rule in self.rules):
            raise ValueError("All rules must refer to configured categories")
        if len({rule.id for rule in self.rules}) != len(self.rules):
            raise ValueError("Rule IDs must be unique")
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore", hide_input_in_errors=True
    )

    app_env: Literal["development", "production", "test"] = "development"
    demo_mode: bool = True
    api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    database_url: str = "sqlite:///./data/app.db"
    config_path: str = "config/config.example.yaml"
    rules_path: str = "config/rules.example.yaml"
    max_message_size_bytes: int = Field(default=500000, ge=1000, le=5000000)
    max_request_size_bytes: int = Field(default=10000000, ge=1000, le=50000000)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    google_client_id: SecretStr = SecretStr("")
    google_client_secret: SecretStr = SecretStr("")
    google_refresh_token: SecretStr = SecretStr("")
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_security: Literal["starttls", "ssl"] = "starttls"
    digest_from: str = ""
    digest_to: str = ""
    output_dir: str = "data/digests"
    scheduler_enabled: bool = False
    poll_seconds: int = Field(default=300, ge=30)

    @model_validator(mode="after")
    def private_production(self) -> Settings:
        if self.app_env == "production" and len(self.api_key.get_secret_value()) < 32:
            raise ValueError("Production requires an API_KEY of at least 32 characters")
        return self

    @property
    def database_path(self) -> str:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("Only SQLite is supported in this MVP")
        return self.database_url.removeprefix("sqlite:///")

    @property
    def rules(self) -> RulesConfig:
        from src.digest.config.yaml_loader import load_yaml_config

        data = load_yaml_config(Path(self.config_path))
        extra_rules = load_yaml_config(Path(self.rules_path)).get("rules", [])
        data["rules"] = data.get("rules", []) + extra_rules
        return RulesConfig.model_validate(data)
