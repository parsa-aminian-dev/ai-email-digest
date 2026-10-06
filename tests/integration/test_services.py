import base64
import json
import sqlite3
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from src.digest.config.settings import Settings
from src.digest.digest.delivery import Delivery
from src.digest.models import EmailMessage
from src.digest.providers.base import DemoProvider
from src.digest.providers.gmail import GMAIL_URL, GmailProvider, map_gmail_message
from src.digest.service import DigestService
from src.digest.storage.repository import EmailRepository


def gmail_message(id="one", body="Hello"):
    return {
        "id": id,
        "internalDate": str(int(datetime.now(UTC).timestamp() * 1000)),
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "Name <person@example.org>"},
                {"name": "Subject", "value": "Synthetic"},
                {"name": "List-Unsubscribe", "value": "<mailto:example@example.org>"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()},
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": base64.urlsafe_b64encode(b"<p>HTML alternative</p>").decode()},
                },
                {
                    "mimeType": "text/plain",
                    "filename": "secret.txt",
                    "body": {"data": base64.urlsafe_b64encode(b"ATTACHMENT").decode()},
                },
            ],
        },
    }


def credentials(settings):
    return Settings(
        **{
            **settings.model_dump(),
            "google_client_id": "test-client",
            "google_client_secret": "test-secret",
            "google_refresh_token": "test-refresh",
        },
        _env_file=None,
    )


def test_gmail_pagination_mapping_and_readonly(test_settings):
    paths = []

    def handler(request):
        paths.append((request.method, str(request.url)))
        if request.url.host == "oauth2.googleapis.com":
            assert b"refresh_token=test-refresh" in request.content
            return httpx.Response(200, json={"access_token": "test-access"})
        assert request.headers["Authorization"] == "Bearer test-access"
        if request.url.path.endswith("/messages"):
            assert request.url.params["q"].startswith("after:")
            if "pageToken" in request.url.params:
                return httpx.Response(200, json={"messages": [{"id": "two"}]})
            return httpx.Response(200, json={"messages": [{"id": "one"}], "nextPageToken": "page2"})
        return httpx.Response(200, json=gmail_message(request.url.path.rsplit("/", 1)[-1]))

    provider = GmailProvider(
        credentials(test_settings), httpx.Client(transport=httpx.MockTransport(handler))
    )
    messages = provider.fetch_messages(datetime.now(UTC) - timedelta(days=1))
    assert [m.id for m in messages] == ["one", "two"]
    assert all(m.body == "Hello" and m.metadata["list_unsubscribe"] for m in messages)
    assert all(method == "GET" or "oauth2" in path for method, path in paths)
    assert provider.failures == 0


def test_gmail_one_message_failure_does_not_abort(test_settings):
    def handler(request):
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "test"})
        if str(request.url).startswith(GMAIL_URL) and request.url.path.endswith("/messages"):
            return httpx.Response(200, json={"messages": [{"id": "bad"}, {"id": "good"}]})
        if request.url.path.endswith("/bad"):
            return httpx.Response(404, json={"error": "gone"})
        return httpx.Response(200, json=gmail_message("good"))

    provider = GmailProvider(
        credentials(test_settings), httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert len(provider.fetch_messages()) == 1 and provider.failures == 1


def test_gmail_retries_and_bounds(test_settings, monkeypatch):
    monkeypatch.setattr("src.digest.http.time.sleep", lambda seconds: None)
    attempts = []

    def handler(request):
        attempts.append(request)
        if len(attempts) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"access_token": "test"})

    from src.digest.http import request_json

    result = request_json(
        httpx.Client(transport=httpx.MockTransport(handler)), "GET", "https://example.org"
    )
    assert result["access_token"] == "test" and len(attempts) == 3
    assert len(map_gmail_message(gmail_message(body="x" * 10000), 100).body) == 100
    with pytest.raises(ValueError):
        GmailProvider(test_settings).fetch_messages()


def test_batch_isolation_checkpoint_and_duplicate_digest(service, monkeypatch):
    now = datetime.now(UTC)
    valid = EmailMessage(
        id="valid",
        sender="a@example.org",
        subject="Invoice",
        body="Please pay",
        received_at=now - timedelta(minutes=30),
    )
    provider = DemoProvider([valid])
    monkeypatch.setattr(service.settings, "demo_mode", False)
    service.provider = provider
    report = service.ingest()
    assert report["processed"] == 1 and service.repository.get_state("gmail_checkpoint")
    assert service.ingest()["duplicates"] == 1
    batch = service.process_batch(
        [
            {"id": "", "sender": "bad"},
            {"id": "two", "sender": "a@example.org"},
            {
                "id": "old",
                "sender": "a@example.org",
                "received_at": (now - timedelta(days=31)).isoformat(),
            },
        ]
    )
    assert (
        batch["report"]["failures"] == 1
        and batch["report"]["processed"] == 1
        and batch["report"]["expired"] == 1
    )
    deliveries = []
    monkeypatch.setattr(service.delivery, "validate", lambda: None)
    monkeypatch.setattr(service.delivery, "send", lambda result: deliveries.append(result.id))
    start, end = now - timedelta(days=1), now
    first = service.generate_digest(start, end, deliver=True)
    second = service.generate_digest(start, end, deliver=True)
    assert first.id == second.id and deliveries == [first.id]
    assert first.health["failures"] == 1


def test_provider_failure_preserves_cursor_and_delivers_health(service, monkeypatch):
    class Failing(DemoProvider):
        def fetch_messages(self, since=None):
            raise httpx.TimeoutException("private credentials")

    service.provider = Failing()
    monkeypatch.setattr(service.settings, "demo_mode", False)
    service.repository.set_state("gmail_checkpoint", "2026-10-05T00:00:00+00:00")
    assert service.ingest()["provider_failures"] == 1
    assert service.repository.get_state("gmail_checkpoint") == "2026-10-05T00:00:00+00:00"
    now = datetime.now(UTC)
    digest = service.generate_digest(now - timedelta(days=1), now)
    assert digest.health["provider_failures"] == 1 and "Degraded processing" in digest.text


def test_partial_provider_failure_preserves_cursor(service, monkeypatch):
    provider = DemoProvider([EmailMessage(id="new", sender="x@example.org")])
    provider.failures = 1
    service.provider = provider
    monkeypatch.setattr(service.settings, "demo_mode", False)
    assert service.ingest()["provider_failures"] == 1
    assert service.repository.get_state("gmail_checkpoint") is None
    assert service.repository.get("new")


def test_uncertain_delivery_is_never_automatically_retried(service, monkeypatch):
    calls = []

    def fail(result):
        calls.append(result.id)
        raise ConnectionError("Accepted then disconnected")

    monkeypatch.setattr(service.delivery, "send", fail)
    now = datetime.now(UTC)
    with pytest.raises(ConnectionError):
        service.generate_digest(now - timedelta(days=1), now, deliver=True)
    digest = service.generate_digest(now - timedelta(days=1), now, deliver=True)
    assert service.repository.delivery_state(digest.id) == "uncertain"
    assert calls == [digest.id]


def test_smtp_uses_tls_and_fixed_recipient(test_settings, monkeypatch, service):
    captured = {}

    class SMTP:
        def __init__(self, host, port, **kwargs):
            captured.update(host=host, port=port)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self, **kwargs):
            captured["tls"] = True

        def login(self, user, password):
            captured["login"] = user

        def send_message(self, message, **kwargs):
            captured.update(kwargs)
            captured["message"] = message

    monkeypatch.setattr("src.digest.digest.delivery.smtplib.SMTP", SMTP)
    monkeypatch.setattr("src.digest.digest.delivery.smtplib.SMTP_SSL", SMTP)
    settings = Settings(
        **{
            **test_settings.model_dump(),
            "demo_mode": False,
            "smtp_host": "smtp.example.org",
            "smtp_user": "owner@example.org",
            "digest_from": "owner@example.org",
            "digest_to": "owner@example.org",
        },
        _env_file=None,
    )
    result = service.builder.build([])
    result.id = "synthetic-digest"
    Delivery(settings).send(result)
    assert captured["tls"] and captured["to_addrs"] == ["owner@example.org"]
    assert captured["message"].is_multipart()
    settings.smtp_security = "ssl"
    Delivery(settings).send(result)
    settings.digest_to = "bad\naddress"
    with pytest.raises(ValueError):
        Delivery(settings).send(result)


def test_migrate_legacy_store_without_raw_addresses(tmp_path):
    path = tmp_path / "legacy.db"
    legacy = {
        "id": "old",
        "sender": "private@example.org",
        "subject": "user@example.org",
        "category": "general",
        "priority": "MEDIUM",
        "summary": "password=secret_value",
    }
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE processed_emails(payload TEXT)")
        conn.execute("INSERT INTO processed_emails VALUES (?)", (json.dumps(legacy),))
    repo = EmailRepository(str(path))
    assert "private@example.org" not in repo.get("old").model_dump_json()
    assert "user@example.org" not in repo.get("old").subject
    with sqlite3.connect(path) as conn:
        assert not conn.execute(
            "SELECT name FROM sqlite_master WHERE name='processed_emails'"
        ).fetchone()


def test_demo_previews_and_purge(service):
    result = service.run_scheduled()
    assert result["delivery"] == "sent"
    assert list(__import__("pathlib").Path(service.settings.output_dir).glob("*.html"))
    service.purge()
    assert service.repository.list_recent() == []
    assert not list(__import__("pathlib").Path(service.settings.output_dir).glob("*.html"))


def test_mock_ai_overview_and_degraded_overview(service, monkeypatch):
    from src.digest.llm.base import MockLLMAdapter

    service.processor.llm_adapter = MockLLMAdapter()
    now = datetime.now(UTC)
    service.process_batch(
        [EmailMessage(id="ai", sender="a@example.org", subject="A question", body="Please reply.")]
    )
    digest = service.generate_digest(now - timedelta(days=1), now + timedelta(seconds=1))
    assert digest.ai_summary_used and digest.health["llm_calls"] == 2
    assert service.repository.get("ai").llm_used

    def fail(payload):
        raise ValueError("Unavailable model")

    monkeypatch.setattr(service.processor.llm_adapter, "summarize", fail)
    degraded = service.generate_digest(now - timedelta(days=1), now + timedelta(seconds=2))
    assert not degraded.ai_summary_used and degraded.health["overview_fallback"] == 1
    assert "Degraded processing" in degraded.text


def test_maintenance_works_without_optional_ai_credentials(test_settings, tmp_path):
    import yaml

    from src.digest.config.yaml_loader import load_yaml_config

    config = load_yaml_config(test_settings.config_path)
    config["llm"]["provider"] = "openai"
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    settings = Settings(**{**test_settings.model_dump(), "config_path": str(path)}, _env_file=None)
    with pytest.raises(ValueError):
        DigestService(settings)
    maintenance = DigestService(settings, initialize_integrations=False)
    maintenance.purge()
    maintenance.close()
