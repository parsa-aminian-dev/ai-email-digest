# Data model

SQLite schema version 2 is initialized transactionally by `EmailRepository`.

| Table | Fields | Purpose |
| --- | --- | --- |
| `records` | ID, received_at, processed_at, minimized JSON | Idempotent processed metadata |
| `state` | key, value | Last successful Gmail checkpoint |
| `runs` | ID, timestamp, metric JSON | Failure counts and run health |
| `budgets` | local calendar day, conservative reserved tokens | Persisted hard AI budget |
| `digests` | interval ID, created_at, rendered JSON, delivery_state | Cached snapshots and delivery receipts |
| `leases` | job name, expiry | Cross-process job coordination |

Records contain sender domain, sanitized/redacted subject, category, five-level priority, enumerated action, optional explicit deadline, bounded summary, confidence, processing/review state, and AI use/fallback flags. Raw sender addresses, recipients, bodies, headers, and attachments are excluded. Received timestamps are timezone aware and stored in UTC. An index supports half-open received-time windows.

Legacy starter `processed_emails` records are migrated into this metadata format with redaction; the legacy table is removed under SQLite secure deletion. No original timestamp existed in the starter, so legacy migration assigns its migration time. Migrations are small and explicit; future schema changes must add a new version and migration test.

Delivery transitions are `pending → sending → sent` or `sending → uncertain`. A crash may leave `sending`. Neither `sending` nor `uncertain` automatically retries. The operator can reconcile as `sent`, or as `pending` only after checking acceptance.

Retention defaults to 30 days. Deduplication is guaranteed within this horizon; older inputs are rejected. Purging or replacing the database resets deduplication and the checkpoint. Metadata stored on disk still requires an encrypted host or volume.
