# Requirements

## Functional requirements

- Collect email data from supported mailbox providers.
- Normalize and redact personal or sensitive data before model processing.
- Categorize and prioritize messages using deterministic rules.
- Generate a digest with a daily schedule and customizable time window.
- Allow optional LLM-assisted summarization with safe prompt boundaries.
- Retain filtered email metadata according to policy.

## Non-functional requirements

- Secure storage of credentials and API keys.
- Respect privacy, consent, and GDPR constraints.
- Support modular provider and model abstractions.
- Keep both deterministic and ML-assisted outputs auditable.
- Provide tests for unit, integration, and security scenarios.
