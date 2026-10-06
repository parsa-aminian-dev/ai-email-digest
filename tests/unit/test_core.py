from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

import pytest
from pydantic import ValidationError

from src.digest.config.settings import DigestConfig, RulesConfig, Settings
from src.digest.config.yaml_loader import load_yaml_config
from src.digest.digest.builder import DigestBuilder
from src.digest.models import EmailMessage, ProcessedEmail
from src.digest.pipeline.processor import EmailProcessor
from src.digest.pipeline.schedule import daily_window
from src.digest.preprocessing.redact import normalize_email_text, redact_sensitive_text
from src.digest.rules.engine import evaluate_rule_engine
from src.digest.storage.repository import BusyJobError, EmailRepository


def message(**updates):
    return EmailMessage.model_validate(
        {"id": "one", "sender": "Name <person@company.example>", "subject": "Meeting", **updates}
    )


def record(**updates):
    return ProcessedEmail.model_validate(
        {
            "id": "one",
            "sender_domain": "example.org",
            "received_at": datetime.now(UTC),
            "category": "general",
            "priority": "MEDIUM",
            **updates,
        }
    )


def test_preprocessing() -> None:
    body = '<style>hidden</style><script>steal()</script><p>Hello &amp; welcome</p><img src="tracking">\n> old reply\n-- \nsignature'
    assert normalize_email_text(body) == "Hello & welcome"
    assert normalize_email_text("Hi\nOn Monday X wrote:\nold") == "Hi"
    assert normalize_email_text("a" * 10000, 100) == "a" * 100
    assert normalize_email_text("") == ""


@pytest.mark.parametrize(
    "secret",
    [
        "DE89 3704 0044 0532 0130 00",
        "4111-1111-1111-1111",
        "+49 170 12345678",
        "9876543210",
        "user@example.com",
        "password=secretvalue",
        "sk-testsecret123456",
        "https://example.com/private?token=secret",
        "eyJabc.abcdef.signature",
    ],
)
def test_redaction(secret: str) -> None:
    assert secret not in redact_sensitive_text(f"Test {secret} text")


def test_dates_preserved() -> None:
    assert redact_sensitive_text("Please pay by 2026-10-07.") == "Please pay by 2026-10-07."


def test_sender_parse_and_timezone() -> None:
    assert message().sender_domain == "company.example"
    assert message(sender="invalid").sender_domain == "unknown"
    with pytest.raises(ValidationError):
        message(received_at="2026-10-06T10:00:00")


def test_rules_use_config_and_locked_sender(test_settings: Settings) -> None:
    config = test_settings.rules
    rule = evaluate_rule_engine(message(body="unsubscribe newsletter"), config)
    assert rule.category == "work" and rule.priority == "HIGH" and rule.locked
    assert rule.llm_required
    assert (
        evaluate_rule_engine(
            message(
                sender="x@external.example", subject="Invoice", body="Please pay by 2026-10-07"
            ),
            config,
        ).deadline
        == "2026-10-07"
    )
    assert (
        evaluate_rule_engine(
            message(
                sender="x@example.org",
                subject="News",
                labels=["CATEGORY_PROMOTIONS"],
                metadata={"list_unsubscribe": True},
            ),
            config,
        ).priority
        == "LOW"
    )
    assert (
        evaluate_rule_engine(
            message(sender="x@example.org", subject="News", metadata={"list_unsubscribe": True}),
            config,
        ).category
        == "newsletters"
    )
    assert (
        evaluate_rule_engine(
            message(sender="x@example.org", subject="Urgent question"), config
        ).priority
        == "HIGH"
    )
    assert (
        evaluate_rule_engine(
            message(sender="x@example.org", subject="Something else"), config
        ).priority
        == "MEDIUM"
    )


def test_validation_rejects_invalid_config(test_settings: Settings, tmp_path: Path) -> None:
    for changes in (
        {"retention_days": 0},
        {"categories": [{"name": "foo"}]},
        {"rules": [{"id": "bad", "when": {}, "category": "unknown", "priority": "HIGH"}]},
    ):
        with pytest.raises(ValidationError):
            RulesConfig.model_validate({**test_settings.rules.model_dump(), **changes})
    with pytest.raises(ValidationError):
        DigestConfig(time="25:00")
    with pytest.raises(ZoneInfoNotFoundError):
        DigestConfig(timezone="No/SuchZone")
    with pytest.raises(ValidationError):
        Settings(app_env="production", api_key="", _env_file=None)
    with pytest.raises(ValueError):
        _ = Settings(database_url="postgres://localhost", _env_file=None).database_path
    with pytest.raises(FileNotFoundError):
        load_yaml_config(tmp_path / "absent.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("[one, two]")
    with pytest.raises(ValueError):
        load_yaml_config(bad)


def test_processing_does_not_mutate_or_persist_raw_content(test_settings: Settings) -> None:
    email = message(
        sender="personal-name@example.org",
        subject="Invoice for user@example.org",
        body="Please pay by 2026-10-07. IBAN DE89370400440532013000",
    )
    original = email.model_dump()
    result = EmailProcessor(settings=test_settings).process(email)
    assert email.model_dump() == original
    serialized = result.model_dump_json()
    assert (
        "personal-name" not in serialized
        and "user@example.org" not in serialized
        and "DE893" not in serialized
    )
    assert result.deadline == "2026-10-07" and result.action_type == "pay"
    assert not result.llm_used
    assert "body" not in result.model_dump()


def test_digest_sort_and_count_aggregation(test_settings: Settings) -> None:
    records = [
        record(id="low", priority="LOW", category="newsletters"),
        record(id="urgent", priority="URGENT", summary="<script>bad</script>"),
        record(id="action", priority="LOW", action_type="reply"),
    ]
    result = DigestBuilder(test_settings.rules).build(records)
    assert result.entries[0].priority == "URGENT"
    assert next(group for group in result.entries if group.category == "newsletters").items == []
    assert "<script>" not in result.html
    assert result.health["processed"] == 3 and result.health["actions"] == 1
    assert "Grouped messages: 1" in result.text


@pytest.mark.parametrize(
    ("day", "hours"),
    [(datetime(2026, 3, 29, 10, tzinfo=UTC), 23), (datetime(2026, 10, 25, 10, tzinfo=UTC), 25)],
)
def test_dst_windows(day: datetime, hours: int) -> None:
    start, end = daily_window(day, DigestConfig(time="09:00", timezone="Europe/Berlin"))
    assert (end - start).total_seconds() == hours * 3600
    assert end <= day


def test_before_schedule_uses_previous_boundary() -> None:
    now = datetime(2026, 10, 6, 5, tzinfo=UTC)
    _, end = daily_window(now, DigestConfig())
    assert end == datetime(2026, 10, 5, 7, tzinfo=UTC)


def test_repository_idempotence_retention_purge_and_budget(tmp_path: Path) -> None:
    repo = EmailRepository(str(tmp_path / "store.db"))
    assert repo.save(record()) and not repo.save(record(subject="overwrite"))
    assert repo.get("one").subject == ""
    assert repo.get("missing") is None
    old = record(id="old", received_at=datetime.now(UTC) - timedelta(days=31))
    repo.save(old)
    assert repo.cleanup(30) == 1
    assert len(repo.list_recent()) == 1
    assert repo.reserve_tokens("2026-10-06", 8, 10)
    assert not repo.reserve_tokens("2026-10-06", 3, 10)
    assert repo.token_usage("2026-10-06") == 8
    repo.set_state("cursor", "one")
    assert repo.get_state("cursor") == "one"
    with repo.lease("job"):
        with pytest.raises(BusyJobError):
            with repo.lease("job"):
                pass
    repo.purge()
    assert (
        repo.list_recent() == []
        and repo.get_state("cursor") is None
        and repo.token_usage("2026-10-06") == 0
    )


@pytest.mark.parametrize(
    "secret",
    [
        "access_token=opaque-demo-value",
        "refresh-token: opaque-demo-value",
        "client_secret=opaque-demo-value",
        "Bearer opaque-demo-value",
    ],
)
def test_oauth_redaction(secret):
    assert "opaque-demo-value" not in redact_sensitive_text(secret)


def test_signature_and_extractive_fallback(test_settings):
    assert normalize_email_text("Hello\nBest regards,\nMy full name") == "Hello"
    email = message(
        subject="Shift changed",
        body="Your shift now starts at 10:00. Please confirm.\nBest regards,\nTeam",
    )
    item = EmailProcessor(settings=test_settings).process(email)
    assert "10:00" in item.summary and "Team" not in item.summary
