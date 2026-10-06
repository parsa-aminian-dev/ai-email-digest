# Privacy and data handling

This is a single-user self-hosted application. Its data-flow documentation is not a legal compliance certification.

1. Gmail read-only API returns message content to backend memory. Attachments are neither downloaded nor analyzed.
2. Normalization strips HTML, tracking images, quoted replies, signatures and excessive whitespace. Configurable bounds limit processing.
3. Deterministic rules classify local content. Only messages needing analysis can reach the AI adapter.
4. The hosted AI receives a sender domain, sanitized subject and redacted/truncated excerpt. Full addresses, recipients, raw headers, HTML and attachments are excluded. Regex redaction does not guarantee anonymity.
5. SQLite retains minimized metadata: ID/time, domain, redacted subject/summary, categories/priorities/actions, and health flags. Run logs contain IDs and metrics, never mail content.
6. Rendered digests go to the configured owner by TLS SMTP. Demo mode writes local HTML/text previews without SMTP. n8n receives only counts/status/digest ID and does not retain execution payloads.

Retention defaults to 30 days and runs after ingestion and scheduled ticks; `cleanup` is also available manually. `purge` deletes local application data, checkpoints and previews. It cannot erase external AI retention, host snapshots, backups, SMTP server logs or already delivered emails.

Configure an encrypted host disk/volume and protect `.env` and backups. This program does not encrypt `.env` or SQLite itself. Tokens are not written to the database. Hosted AI remains an external privacy boundary; `store: false` is not a zero-retention promise. Review the provider's [data controls](https://developers.openai.com/api/docs/guides/your-data) and applicable regional processing requirements before enabling it. Cloud analysis is disabled by default.
