# AI Email Digest

A privacy-aware system that summarizes incoming email into a daily digest using deterministic rules plus LLM-assisted summarization.

## Structure

This repository is organized to support:
- provider integrations (Gmail and other mailbox sources)
- normalization and redaction of email content
- deterministic categorization and priority rules
- optional LLM summarization with safety guardrails
- pipelines for processing, retention, and delivery

## Getting started

1. Copy `.env.example` to `.env` and update secrets.
2. Copy `config/config.example.yaml` and adjust categories, filters, and digest timing.
3. Run with Docker Compose:
   ```bash
   docker compose up --build
   ```
4. Review docs in `docs/` for architecture, requirements, and security guidance.

## Notes

- Do not commit real credentials or mailbox data.
- Keep prompt templates versioned under `prompts/`.
- Place exported workflow definitions under `n8n/workflows/` without credentials.
