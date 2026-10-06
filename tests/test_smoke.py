from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from src.digest.api.main import create_app
from src.digest.config.settings import Settings
from src.digest.service import DigestService


def test_healthcheck(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/demo/digest").status_code == 200
        assert "Your daily email digest" in client.get("/demo/digest").text


def test_process_batch_generates_digest(test_settings: Settings) -> None:
    with TestClient(create_app(test_settings)) as client:
        response = client.post(
            "/emails/process",
            json={
                "messages": [
                    {
                        "id": "m-1",
                        "sender": "billing@payments.example",
                        "subject": "Payment invoice due",
                        "body": "Your invoice is due today. Please pay 250 USD.",
                    },
                    {
                        "id": "m-2",
                        "sender": "hello@newsletter.example",
                        "subject": "Weekly roundup",
                        "body": "This is a newsletter with unsubscribe info",
                    },
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["digest"]["health"]["processed"] == 2
        assert data["items"][0]["category"] == "finance"
        assert data["items"][0]["action_type"] == "pay"
        assert "sender" not in data["items"][0]
        retry = client.post(
            "/process", json={"messages": [{"id": "m-1", "sender": "same@example.org"}]}
        )
        assert retry.json()["report"]["duplicates"] == 1
        assert client.get("/items?limit=-1").status_code == 422


def test_auth_and_safe_validation(test_settings: Settings) -> None:
    settings = Settings(**{**test_settings.model_dump(), "api_key": "x" * 32}, _env_file=None)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/items").status_code == 401
        response = client.post(
            "/emails/process", headers={"X-API-Key": "x" * 32}, json={"messages": "SECRET-INPUT"}
        )
        assert response.status_code == 422
        assert "SECRET-INPUT" not in response.text
        assert client.get("/docs", headers={"X-API-Key": "x" * 32}).status_code == 200


def test_api_digest_and_limits(test_settings: Settings) -> None:
    settings = test_settings.model_copy(update={"max_request_size_bytes": 1000})
    with TestClient(create_app(settings)) as client:
        assert client.post("/emails/process", content="x" * 1001).status_code == 413
        now = datetime.now(UTC)
        payload = {
            "start": (now - timedelta(days=1)).isoformat(),
            "end": now.isoformat(),
            "deliver": True,
        }
        response = client.post("/digests", json=payload)
        assert response.status_code == 200
        assert response.json()["delivery"] == "sent"
        assert client.post("/digests", json={"start": now.isoformat()}).status_code == 422
        assert (
            client.post(
                "/digests", json={"start": now.isoformat(), "end": now.isoformat()}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/digests", json={"start": "2026-01-01T10:00:00", "end": "2026-01-02T10:00:00"}
            ).status_code
            == 422
        )
        assert client.get("/demo").json()["digest"]["html"]
        assert client.post("/emails/ingest").status_code == 200
        assert client.post("/jobs/tick").status_code == 200


def test_no_demo_in_live_mode(test_settings: Settings, service: DigestService) -> None:
    settings = test_settings.model_copy(update={"demo_mode": False})
    with TestClient(create_app(settings, service)) as client:
        assert client.get("/demo").status_code == 404
        assert client.get("/demo/digest").status_code == 404
