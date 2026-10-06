from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

import httpx

from src.digest.config.settings import Settings
from src.digest.http import request_json
from src.digest.models import EmailMessage
from src.digest.providers.base import MailProvider

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"


def map_gmail_message(raw: dict[str, Any], max_bytes: int = 500000) -> EmailMessage:
    payload = raw.get("payload", {})
    headers = {str(h["name"]).lower(): str(h["value"]) for h in payload.get("headers", [])}
    plain: list[str] = []
    html: list[str] = []
    remaining = max_bytes

    def walk(part: dict[str, Any], depth: int = 0) -> None:
        nonlocal remaining
        if depth > 20 or remaining <= 0 or part.get("filename"):
            return
        content_type = str(part.get("mimeType", "")).lower()
        data = part.get("body", {}).get("data", "")
        if content_type in {"text/plain", "text/html"} and data:
            # Bound decoding before allocating memory; never download attachments.
            encoded = data[: ((remaining + 2) // 3) * 4]
            decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))[:remaining]
            remaining -= len(decoded)
            part_headers = {
                str(h["name"]).lower(): str(h["value"]) for h in part.get("headers", [])
            }
            import re

            charset = re.search(
                r'charset=["\']?([\w-]+)', part_headers.get("content-type", ""), re.I
            )
            encoding = charset.group(1) if charset else "utf-8"
            try:
                text = decoded.decode(encoding, errors="replace")
            except LookupError:
                text = decoded.decode("utf-8", errors="replace")
            (plain if content_type == "text/plain" else html).append(text)
        for child in part.get("parts", []):
            walk(child, depth + 1)

    walk(payload)
    return EmailMessage(
        id=raw["id"],
        sender=headers.get("from", ""),
        subject=headers.get("subject", "")[:2000],
        body="\n".join(plain or html),
        labels=raw.get("labelIds", []),
        received_at=datetime.fromtimestamp(int(raw["internalDate"]) / 1000, UTC),
        metadata={"list_unsubscribe": bool(headers.get("list-unsubscribe"))},
    )


class GmailProvider(MailProvider):
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(timeout=30)
        self._owns_client = client is None
        self.failures = 0

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def fetch_messages(self, since: datetime | None = None) -> list[EmailMessage]:
        self.failures = 0
        secrets = (
            self.settings.google_client_id,
            self.settings.google_client_secret,
            self.settings.google_refresh_token,
        )
        if not all(value.get_secret_value() for value in secrets):
            raise ValueError("Gmail OAuth credentials are required")
        token = request_json(
            self.client,
            "POST",
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "client_id": secrets[0].get_secret_value(),
                "client_secret": secrets[1].get_secret_value(),
                "refresh_token": secrets[2].get_secret_value(),
            },
        )
        headers = {"Authorization": f"Bearer {token['access_token']}"}
        params: dict[str, Any] = {"maxResults": 100, "includeSpamTrash": False}
        if since:
            params["q"] = f"after:{int(since.timestamp())}"
        messages: list[EmailMessage] = []
        seen_pages: set[str] = set()
        while True:
            page = request_json(self.client, "GET", GMAIL_URL, params=params, headers=headers)
            for item in page.get("messages", []):
                try:
                    raw = request_json(
                        self.client,
                        "GET",
                        f"{GMAIL_URL}/{item['id']}",
                        params={"format": "full"},
                        headers=headers,
                    )
                    messages.append(map_gmail_message(raw, self.settings.max_message_size_bytes))
                except Exception:
                    # Retry this ID next poll by leaving the high-water mark unchanged.
                    self.failures += 1
            next_page = page.get("nextPageToken")
            if not next_page:
                break
            if next_page in seen_pages:
                raise ValueError("Repeated Gmail page token")
            seen_pages.add(next_page)
            params["pageToken"] = next_page
        return messages
