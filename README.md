# AI Email Digest

A single-mailbox, privacy-first daily Gmail digest. Python/FastAPI processes mail with configurable rules, optional validated AI, SQLite metadata storage, and HTML/plain-text digests. n8n can trigger the jobs; a built-in scheduler is also available.

[Open the standalone sample digest](docs/demo-digest.html), or run the demo below. See [local validation results](docs/validation.md) for completed checks and the Docker storage limitation on the development machine.

**Try the complete demo without credentials:**

```bash
docker compose up --build --detach --wait
```

Open **http://localhost:8000/demo/digest** for the sample digest and **http://localhost:8000/docs** for the API. Startup processes seven synthetic emails and writes the rendered files to the `digest_data` Docker volume. No Gmail, SMTP, or AI calls occur with the default configuration.

To stop the application, run `docker compose down`. The named volume preserves metadata until retention cleanup or an explicit purge.

## Run locally

Python 3.12 is required. From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m src.digest.cli demo
uvicorn src.digest.api.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

The CLI prints the digest and the generated HTML file path. It uses production code and synthetic fixtures packaged under `src/digest/demo.py`; tests are not runtime dependencies.

## Connect your mailbox

1. Copy `.env.example` to `.env` and copy `config/config.example.yaml` to `config/config.yaml`.
2. Set `CONFIG_PATH=config/config.yaml`, `DEMO_MODE=false`, and `APP_ENV=production`. Set `API_KEY` to a random value of at least 32 characters. Example generator: `python -c 'import secrets; print(secrets.token_urlsafe(32))'`.
3. Follow [Gmail setup](docs/setup-gmail.md) to configure a read-only OAuth client and the three `GOOGLE_*` environment variables.
4. Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `DIGEST_FROM`, and `DIGEST_TO`. The recipient is fixed in configuration. SMTP uses verified TLS; choose `starttls` on port 587 or `ssl` on port 465.
5. Set your categories, sender rules, daily time, time zone, language (`en`/`de`), and retention in YAML. If you customize categories, update `RULES_PATH` rules to reference those categories.
6. Choose a scheduler: set `SCHEDULER_ENABLED=true`, or follow [n8n setup](docs/setup-n8n.md). Keep the laptop/server awake at digest time.
7. Start with `docker compose up --build --detach --wait`. Changes to configuration require restarting the backend. For Docker, SQLite lives at `/app/data/app.db` regardless of the local `DATABASE_URL` value.

The first live poll retrieves the retention window (30 days by default). Later polls start from the last successful checkpoint with a one-hour overlap; message IDs prevent duplicate processing. Read and unread messages are both considered. Attachments, spam, and trash are excluded. A failed page or message leaves the checkpoint unchanged so the next poll retries it.

Every tick polls Gmail, then generates the most recent daily interval ending at your configured local time. Each interval is a persisted snapshot and is delivered once. Polling can delay delivery by up to `POLL_SECONDS` (five minutes by default). Before today's boundary, the latest boundary is yesterday's; a newly started deployment can therefore deliver yesterday's interval. DST windows may cover 23 or 25 hours. The system does not backfill every missed daily digest after prolonged downtime.

## Optional AI

Rules and short extractive summaries work with `llm.provider: disabled` (the default). Set `llm.provider: openai` in YAML and `OPENAI_API_KEY` in `.env` to enable analysis and an AI overview. `mock` is available only in demo mode.

The hosted adapter uses [OpenAI structured output](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), `store: false`, no tools, strict local schema validation, and a persisted daily token budget. It sends only a sender domain, sanitized subject, redacted excerpt, category names, and language. All API retries reserve budget before sending. The conservative byte-based reservation includes output and overhead and is not refunded on failures; reported token usage is the provider's actual usage when available. A model or budget failure falls back to rules and is shown in processing health. The overall overview also uses the same budget.

Redaction is pattern based, not a complete anonymizer. Names, locations, and sensitive prose can remain. Assess the [provider's data controls](https://developers.openai.com/api/docs/guides/your-data) before enabling cloud AI. This project makes no monthly cost guarantee; set an account spending limit as well as the local token budget.

## API

All endpoints except `/health` require `X-API-Key` when `API_KEY` is configured. API docs require the same header; use the CLI or an HTTP client for protected access. Production refuses to start without a strong API key. Docker binds the API only to localhost; do not expose it publicly without a TLS reverse proxy and further access controls.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness |
| `POST /emails/process` | Validate and process a batch of canonical messages |
| `POST /emails/ingest` | Poll Gmail, or synthetic mail in demo mode |
| `POST /digests` | Generate a persisted interval snapshot, optionally deliver it |
| `POST /jobs/tick` | Poll, deliver the due digest, enforce retention |
| `GET /items?limit=20` | Inspect minimized processing metadata |
| `GET /demo` | Demo digest JSON |
| `GET /demo/digest` | Safe demo HTML, available only in demo mode |

Example message batch (synthetic only):

```json
{
  "messages": [{
    "id": "synthetic-001",
    "sender": "billing@payments.example",
    "subject": "Invoice due",
    "body": "Please pay by 2026-10-07.",
    "received_at": "2026-10-06T08:00:00+02:00",
    "labels": ["INBOX"],
    "metadata": {"list_unsubscribe": false}
  }]
}
```

Each message is validated separately. A malformed entry cannot reject other messages. Batch size is limited to 500, request size to 10 MB, and body normalization to 4,000 characters by default. Sender addresses, raw bodies, raw headers, and attachments are never persisted. Stored subjects and summaries are normalized, bounded, and redacted. `/process` remains an alias for the starter API.

`POST /digests` accepts `{"start": "…timezone-aware ISO date…", "end": "…timezone-aware ISO date…", "deliver": false}`. Omit both dates for the scheduled window. Windows use `[start, end)`. Repeating the same interval returns the same snapshot, even if new metadata arrives later. Generation and delivery share a durable ID; requesting delivery of an existing preview uses that snapshot.

## Commands and recovery

```bash
python -m src.digest.cli ingest
python -m src.digest.cli digest
python -m src.digest.cli digest --deliver
python -m src.digest.cli run
python -m src.digest.cli cleanup
python -m src.digest.cli delivery-status --id DIGEST_ID
```

SMTP cannot guarantee exactly-once delivery across a crash or lost acknowledgement. A delivery claim is persisted before sending. An exception marks it `uncertain`; a crash may leave `sending`. Neither state is automatically retried. Check the recipient's inbox/SMTP logs, then reconcile explicitly:

```bash
python -m src.digest.cli resolve-delivery --id DIGEST_ID --state sent
# Only after verifying the message was NOT accepted, explicitly permit a resend:
python -m src.digest.cli resolve-delivery --id DIGEST_ID --state pending
```

A crashed processing job has a one-hour lease; successful jobs release it immediately. Stop other processing before purging all metadata, checkpoints, delivery history, budgets, and local previews:

```bash
docker compose stop backend
# Do not start this container's scheduler or API; execute only the maintenance command.
docker compose run --rm --no-deps backend python -m src.digest.cli purge
```

Purging resets deduplication/checkpoints. The next poll can reprocess retained Gmail messages and redeliver intervals. Backups, remote AI retention, and digests already delivered to your inbox are outside the purge command's reach. Use an encrypted host disk/volume for data and `.env`; filesystem permissions do not provide encryption.

## Quality checks

```bash
ruff check src tests
ruff format --check src tests
mypy src/digest
pytest --cov=src/digest --cov-report=term-missing
pip-audit -r requirements.txt
pre-commit install
pre-commit run --all-files
```

CI runs lint, format, types, core coverage (minimum 80%), dependency auditing, a Docker demo smoke test, and Gitleaks history scanning. Tests mock Gmail, AI, and SMTP; they do not use credentials or send real mail.

See [architecture](docs/architecture.md), [data model](docs/data-model.md), [security](docs/security.md), [privacy](docs/privacy-and-gdpr.md), [MVP requirement mapping](docs/mvp-status.md), and [decisions](docs/decisions/ADR-0002.md).

Immediate alerts, feedback learning, a history web UI, attachment analysis, local-model support, and multi-user hosting are post-MVP features. The demo HTML is a digest preview, not a mailbox management UI.
