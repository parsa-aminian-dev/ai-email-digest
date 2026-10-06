from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from src.digest.models import DigestResult, ProcessedEmail
from src.digest.preprocessing.redact import safe_text


class BusyJobError(RuntimeError):
    pass


class EmailRepository:
    """SQLite metadata store. Transactions coordinate API and scheduler processes."""

    def __init__(self, database_path: str = "data/app.db") -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.database_path.chmod(0o600)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA secure_delete=ON")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, received_at TEXT NOT NULL, processed_at TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS records_received ON records(received_at)")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, at TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS budgets (day TEXT PRIMARY KEY, tokens INTEGER NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS digests (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL, delivery_state TEXT NOT NULL DEFAULT 'pending')"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS leases (name TEXT PRIMARY KEY, expires_at TEXT NOT NULL)"
            )
            # Migrate the starter's legacy schema, eliminating raw sender addresses/payloads.
            legacy = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='processed_emails'"
            ).fetchone()
            if legacy:
                for row in conn.execute("SELECT payload FROM processed_emails").fetchall():
                    old = json.loads(row["payload"])
                    now = datetime.now(UTC)
                    sender = parseaddr(str(old.get("sender", "")))[1].lower()
                    item = ProcessedEmail(
                        id=old["id"],
                        received_at=now,
                        sender_domain=sender.rsplit("@", 1)[1] if "@" in sender else "unknown",
                        subject=safe_text(old.get("subject", ""), 300),
                        category=old["category"],
                        priority=old["priority"],
                        action_type=old.get("action_type", "none"),
                        summary=safe_text(old.get("summary", "")),
                        confidence=old.get("confidence", 0),
                        llm_used=old.get("llm_used", False),
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO records VALUES (?, ?, ?, ?)",
                        (
                            item.id,
                            now.isoformat(),
                            item.processed_at.isoformat(),
                            item.model_dump_json(),
                        ),
                    )
                conn.execute("DROP TABLE processed_emails")
            conn.execute("PRAGMA user_version=2")

    def get(self, message_id: str) -> ProcessedEmail | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM records WHERE id=?", (message_id,)).fetchone()
        return ProcessedEmail.model_validate_json(row["payload"]) if row else None

    def save(self, item: ProcessedEmail) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO records VALUES (?, ?, ?, ?)",
                (
                    item.id,
                    item.received_at.astimezone(UTC).isoformat(),
                    item.processed_at.isoformat(),
                    item.model_dump_json(),
                ),
            )
            return cursor.rowcount == 1

    def list_recent(self, limit: int = 20) -> list[ProcessedEmail]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM records ORDER BY received_at DESC, id LIMIT ?", (limit,)
            ).fetchall()
        return [ProcessedEmail.model_validate_json(row["payload"]) for row in rows]

    def list_period(self, start: datetime, end: datetime) -> list[ProcessedEmail]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM records WHERE received_at >= ? AND received_at < ? ORDER BY received_at, id",
                (start.astimezone(UTC).isoformat(), end.astimezone(UTC).isoformat()),
            ).fetchall()
        return [ProcessedEmail.model_validate_json(row["payload"]) for row in rows]

    def get_state(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_state(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO state VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def record_run(self, report: dict[str, Any], at: datetime | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs(at, payload) VALUES (?, ?)",
                ((at or datetime.now(UTC)).isoformat(), json.dumps(report)),
            )

    def run_health(self, start: datetime, end: datetime) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM runs WHERE at >= ? AND at < ?",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        reports = [json.loads(row["payload"]) for row in rows]
        keys = ("failures", "provider_failures", "llm_fallbacks", "llm_calls", "llm_tokens")
        return {key: sum(int(report.get(key, 0)) for report in reports) for key in keys}

    def reserve_tokens(self, day: str, tokens: int, limit: int) -> bool:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT OR IGNORE INTO budgets VALUES (?, 0)", (day,))
            return (
                conn.execute(
                    "UPDATE budgets SET tokens=tokens+? WHERE day=? AND tokens+? <= ?",
                    (tokens, day, tokens, limit),
                ).rowcount
                == 1
            )

    def token_usage(self, day: str) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT tokens FROM budgets WHERE day=?", (day,)).fetchone()
        return row["tokens"] if row else 0

    def get_digest(self, digest_id: str) -> DigestResult | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM digests WHERE id=?", (digest_id,)).fetchone()
        return DigestResult.model_validate_json(row["payload"]) if row else None

    def save_digest(self, result: DigestResult) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO digests(id, created_at, payload) VALUES (?, ?, ?)",
                (result.id, result.generated_at.isoformat(), result.model_dump_json()),
            )

    def claim_delivery(self, digest_id: str) -> bool:
        with self._connect() as conn:
            return (
                conn.execute(
                    "UPDATE digests SET delivery_state='sending' WHERE id=? AND delivery_state='pending'",
                    (digest_id,),
                ).rowcount
                == 1
            )

    def mark_delivery(self, digest_id: str, state: str) -> None:
        if state not in {"sent", "uncertain", "pending"}:
            raise ValueError("Invalid delivery state")
        with self._connect() as conn:
            conn.execute("UPDATE digests SET delivery_state=? WHERE id=?", (state, digest_id))

    def delivery_state(self, digest_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT delivery_state FROM digests WHERE id=?", (digest_id,)
            ).fetchone()
        return row["delivery_state"] if row else None

    @contextmanager
    def lease(self, name: str) -> Iterator[None]:
        now = datetime.now(UTC)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM leases WHERE name=? AND expires_at < ?", (name, now.isoformat())
            )
            if (
                conn.execute(
                    "INSERT OR IGNORE INTO leases VALUES (?, ?)",
                    (name, (now + timedelta(hours=1)).isoformat()),
                ).rowcount
                != 1
            ):
                raise BusyJobError("Job already running")
        try:
            yield
        finally:
            with self._connect() as conn:
                conn.execute("DELETE FROM leases WHERE name=?", (name,))

    def cleanup(self, retention_days: int, now: datetime | None = None) -> int:
        cutoff = ((now or datetime.now(UTC)) - timedelta(days=retention_days)).isoformat()
        with self._connect() as conn:
            conn.execute("PRAGMA secure_delete=ON")
            count = conn.execute("DELETE FROM records WHERE received_at < ?", (cutoff,)).rowcount
            conn.execute("DELETE FROM runs WHERE at < ?", (cutoff,))
            conn.execute("DELETE FROM digests WHERE created_at < ?", (cutoff,))
            conn.execute("DELETE FROM budgets WHERE day < ?", (cutoff[:10],))
        return count

    def purge(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA secure_delete=ON")
            for table in ("records", "state", "runs", "budgets", "digests", "leases"):
                conn.execute(f"DELETE FROM {table}")
        with self._connect() as conn:
            conn.execute("VACUUM")
