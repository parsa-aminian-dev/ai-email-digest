# Security and threat model

| Threat | Implemented boundary | Remaining limitation |
| --- | --- | --- |
| Email instructs the AI to execute commands | No tools/actions; JSON data in a separate user turn | An AI can still produce an inaccurate label |
| AI invents output fields or deadlines | Strict enums/lengths, configured category validation, evidence/deadline grounding | Grounded text does not prove semantic correctness |
| AI downgrades an employer/security signal | Explicit rules lock category/priority; HIGH/URGENT hints cannot be lowered | Sender headers can be spoofed; rules do not authenticate identity |
| HTML/phishing/tracking in a digest | Normalized/redacted text, escaping, no email-derived links/images; demo CSP | Mail clients have their own rendering policies |
| Secrets sent to hosted AI | Pattern redaction of subject and excerpt; no headers, recipients, raw HTML or attachments | Names and sensitive prose may remain |
| API misuse or oversized input | Production API key, localhost binding, bounded request/batch/body sizes | No public internet deployment/rate limiter is supplied |
| Retry sends duplicate digest | SQLite snapshot and delivery claim; ambiguous sends require reconciliation | SMTP offers no transaction across the database and recipient server |
| Raw data appears in logs | Structured correlation IDs, counts, durations and exception class names | Operators must also configure reverse proxies and infrastructure logs |
| Leaked repository credentials | Ignore rules, narrow Docker build context, Gitleaks pre-commit/CI | Hooks must be installed; host backups and secret stores remain operator responsibilities |

API validation responses deliberately exclude Pydantic input values. The default server command disables access logs. Production API keys are required to be at least 32 characters; generate them randomly. No HTTP endpoint purges data; purge is a local maintenance CLI command.

SQLite files and digest previews have owner-only permissions. Docker runs as an unprivileged user with a read-only root filesystem, no Linux capabilities and a writable data volume. Credentials are environment-only; Gmail access tokens are held in memory. An encrypted host/volume is required for at-rest protection; the app does not implement its own encryption system.

Tests include malicious English/German instructions, fake system messages, executable HTML, invalid schema output, hallucinated evidence/deadlines, sender precedence, redacted model payloads, timeouts, malformed messages, and ambiguous SMTP acceptance. Production integration tests require operator credentials and are deliberately not performed by CI.
