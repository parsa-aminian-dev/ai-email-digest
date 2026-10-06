# Data model

## Core entities

- `EmailMessage`
  - id, provider_id, sender, subject, body, received_at, labels, is_read
- `DigestEntry`
  - category, priority, summary, action_items, source_message_ids
- `DigestResult`
  - generated_at, interval_start, interval_end, entries, metadata
- `RetentionPolicy`
  - ttl_days, delete_after, dry_run

## Normalized fields

All provider-specific event payloads are converted to a canonical internal representation before rule evaluation or LLM processing.

## Security constraints

Sensitive fields should be redacted or excluded before passing data to external model providers.
