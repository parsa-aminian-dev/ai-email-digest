# Security

## Principles

- Principle of least privilege for API tokens and mailbox scopes.
- Redaction of names, addresses, account numbers, and secrets before summarization.
- Prompt-injection mitigations: do not trust email content as instructions to the model.
- Audit logs for digest generation and storage access.

## Recommended controls

- Store secrets in `.env` or a secret manager, never in source files.
- Restrict outbound network access for model calls.
- Validate and sanitize all untrusted email inputs.
- Keep rule logic deterministic and reviewable.
