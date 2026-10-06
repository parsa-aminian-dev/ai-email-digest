# AI Email Digest — Project Definition & Requirements

Phase 1 deliverable · Draft v0.1 · 06.10.2026 · Awaiting approval before Phase 2

## 1. Project Name Suggestions

- **InboxBrief** — short, memorable, describes the outcome.
- **DigestGuard** — emphasizes the privacy and prompt-injection-safe angle, which is a strong differentiator for a portfolio.
- **MailDigest** — plain and searchable.
- **ai-email-digest** — the working repository name used in this document.

Recommendation: use `ai-email-digest` as the repository slug and decide on a brand name later; it does not affect the design.

## 2. Problem Statement

A personal mailbox receives dozens of messages per day from very different sources: work, banks, payment providers, shops, social and career platforms, newsletters and private contacts. Most of them need no action, but a few are time-critical (a changed shift, a payment problem, a delivery that needs a signature). Checking everything manually costs time and attention, and important messages get buried between marketing and notifications.

Existing mail filters are static (labels and rules) and do not understand content. Pure LLM summarizers, on the other hand, are expensive, slow, privacy-invasive if they ship every email to a third party, and vulnerable to malicious email content.

The project solves this by combining deterministic rules with selective, minimized and validated LLM analysis to produce one concise, prioritized daily digest.

## 3. Target User

**Primary user:** a single individual (the repository owner) running the system for their own Gmail mailbox, self-hosted on a laptop, home server or small cloud VM.

**Secondary audience:** recruiters and engineers reviewing the repository as a portfolio piece. This means the repository must be readable, reproducible with mock data, and must visibly demonstrate engineering decisions.

Multi-user or SaaS operation is explicitly not a goal.

## 4. Goals

- **G1:** Turn a day's emails into one concise, prioritized, personalized digest.
- **G2:** Classify emails into a configurable category set and assign one of five priorities.
- **G3:** Detect required actions (reply, confirm, pay, attend, submit, and so on) and surface them clearly.
- **G4:** Use the LLM only where it adds value; handle clear-cut cases with deterministic rules to save tokens, cost and latency.
- **G5:** Treat all email content as untrusted input and minimize what leaves the machine.
- **G6:** Be observable, testable and reproducible: logging without sensitive data, mocked tests, Docker setup.
- **G7:** Document decisions (ADRs) so the project demonstrates engineering judgment, not only working code.

## 5. Scope

**In scope for the project overall**

- Gmail as the first mail provider, behind an abstraction that allows other providers later.
- Ingestion, preprocessing, rule-based filtering, classification, priority detection, action extraction, summarization.
- Daily digest generation and delivery by email at a configurable time.
- Configurable categories, sender rules and digest time (via a config file).
- Local persistence of processing metadata with retention and deletion.
- Logging, tests, documentation, Docker-based deployment.

**In scope later (post-MVP):** immediate alerts for important emails, a review/history interface, additional providers, local LLM support, feedback-based learning.

## 6. Out of Scope

- Replying to, sending, deleting or moving emails on the user's behalf. The system is strictly **read-only** with respect to the mailbox.
- Multi-tenant hosting, user accounts, billing.
- Attachment content analysis (OCR, PDF parsing) in the MVP.
- A full web UI in the MVP (config file and email digest are enough).
- Training or fine-tuning models.
- Mobile apps.

## 7. Actors

- **User** — configures the system, reads the digest, optionally corrects classifications.
- **Scheduler / Automation Engine** (n8n or cron) — triggers ingestion and digest generation.
- **Mail Provider** (Gmail) — source of emails. Passive system actor.
- **LLM Provider** — external analysis service. Passive system actor and a privacy boundary.
- **Notification / Email Delivery Provider** — delivers the digest (Gmail send scope or SMTP).
- **Malicious Sender** — a threat actor whose email content tries to manipulate the system. Not a real use-case actor, but modeled explicitly in the threat model.

## 8. External Systems

- **Gmail API** — OAuth2, read-only scope (`gmail.readonly`).
- **LLM API** — provider to be decided (see open questions); accessed through a thin adapter interface so it can be swapped, including for a local model.
- **Email delivery** — SMTP or Gmail send. If the Gmail send scope is used, it should be a separate, narrowly scoped credential; SMTP with an app password to the user's own address is simpler.
- **n8n** — workflow engine for triggers, scheduling and connectors (see architecture).
- **Docker / GitHub** — packaging and publication.

## 9. Main Use Cases

Only use cases that justify their existence are listed. The diagram comes in Phase 2.

- **UC-01 Ingest new emails** — Scheduler triggers retrieval of new messages from Gmail.
- **UC-02 Process email** — Pipeline runs preprocessing, rules, classification, priority, action extraction and, when necessary, LLM analysis. Includes UC-03 to UC-06 as steps.
- **UC-03 Classify email** — Assign a category from the configured set.
- **UC-04 Determine priority** — Assign URGENT, HIGH, MEDIUM, LOW or INFORMATIONAL.
- **UC-05 Extract action items** — Detect required actions and optional deadlines.
- **UC-06 Summarize** — Produce a short summary only for relevant emails; group trivial ones into counts.
- **UC-07 Generate daily digest** — Aggregate processed records for the period into a digest.
- **UC-08 Deliver daily digest** — Send the digest at the configured time.
- **UC-09 Configure system** — Edit categories, rules, digest time, retention and notification rules.
- **UC-10 Review processing history** — Inspect what was processed, with what result and whether the LLM was used (post-MVP, CLI first).
- **UC-11 Correct classification / mark as important** — User feedback that creates a sender rule (post-MVP).
- **UC-12 Send immediate alert** — Notify for URGENT emails outside the digest (post-MVP).

## 10. Functional Requirements

Priority key: **M** = MVP, **P** = post-MVP.

**Ingestion**

- **FR-001 (M):** The system shall retrieve newly received emails from the user's mailbox since the last successful run.
- **FR-002 (M):** The system shall process each email at most once (idempotency via provider message ID).
- **FR-003 (M):** The system shall access the mailbox read-only.
- **FR-004 (P):** The system shall support additional mail providers through a provider interface.

**Preprocessing**

- **FR-005 (M):** The system shall normalize emails (strip HTML, quoted replies, signatures, tracking pixels and excessive whitespace) and truncate the text to a configurable maximum length.
- **FR-006 (M):** The system shall handle empty, malformed or oversized emails without failing the whole run.
- **FR-007 (M):** The system shall redact obvious sensitive patterns (IBANs, card numbers, long digit sequences, phone numbers, tokens) before any content is sent to an LLM.

**Rules and classification**

- **FR-008 (M):** The system shall apply configurable deterministic rules (sender, domain, subject patterns, Gmail labels, `List-Unsubscribe` header) before invoking the LLM.
- **FR-009 (M):** The system shall classify each email into a category from a configurable category list.
- **FR-010 (M):** The system shall assign a priority level (URGENT, HIGH, MEDIUM, LOW, INFORMATIONAL) to each email.
- **FR-011 (M):** The system shall invoke the LLM only for emails that rules cannot resolve with sufficient confidence or that require summarization or action extraction.

**Analysis**

- **FR-012 (M):** The system shall determine whether an action is required and extract an action type (reply, confirm, pay, attend, submit, change, contact, none) with an optional deadline.
- **FR-013 (M):** The system shall generate a concise summary for emails above a configurable priority threshold and shall aggregate low-value emails into counts per category.
- **FR-014 (M):** The system shall validate all LLM output against a strict schema (enumerated categories, priorities and action types, length limits) and fall back to rule-based results if validation fails.
- **FR-015 (M):** The system shall never execute actions or follow instructions found in email content.

**Digest**

- **FR-016 (M):** The system shall generate a daily digest grouped by priority and category, with an overall short AI summary.
- **FR-017 (M):** The system shall deliver the digest at a configurable time and time zone.
- **FR-018 (M):** The system shall include a processing-health section in the digest (number of emails processed, failures, LLM fallback count).
- **FR-019 (M):** The system shall render the digest safely (escape all email-derived text; no remote images or links that could leak data).

**Configuration and storage**

- **FR-020 (M):** The system shall load categories, rules, digest time, retention and LLM settings from a validated configuration file.
- **FR-021 (M):** The system shall store processed metadata and shall delete it after a configurable retention period.
- **FR-022 (M):** The system shall provide a command to delete all stored data.

**Post-MVP**

- **FR-023 (P):** The system shall send immediate alerts for emails above a configurable urgency.
- **FR-024 (P):** The system shall allow the user to review processing history and correct classifications.
- **FR-025 (P):** The system shall learn sender rules from user corrections.

## 11. Non-Functional Requirements

- **NFR-SEC-01 Security:** Least-privilege OAuth scopes; secrets only via environment variables or a secret store; tokens never logged; dependencies pinned and scanned.
- **NFR-PRIV-01 Privacy:** Data minimization toward the LLM (see section 12); no email bodies persisted by default; local-first storage; retention limits enforced.
- **NFR-REL-01 Reliability:** A failure in one email, the Gmail API or the LLM must not abort the run; retries with exponential backoff; the digest is still delivered with a degraded-mode notice.
- **NFR-REL-02 Idempotency:** Re-running a job never produces duplicate records or duplicate digests.
- **NFR-PERF-01 Performance:** Processing 100 emails should complete within a few minutes; a daily run is not latency-critical.
- **NFR-COST-01 Cost:** Target under about €1 per month at typical volume, achieved by rule-based short-circuiting, batching and a small model; a configurable daily token budget acts as a hard stop.
- **NFR-MAINT-01 Maintainability:** Clear module boundaries, typed code, linting and formatting, at least 80% coverage on core logic, ADRs for key decisions.
- **NFR-SCALE-01 Scalability:** Designed for one mailbox and a few hundred emails per day; scaling beyond that is deliberately not a goal, but the provider and LLM interfaces must not block it.
- **NFR-OBS-01 Observability:** Structured logs with correlation IDs, run-level metrics (counts, durations, LLM calls, tokens, failures), no sensitive content in logs.
- **NFR-USE-01 Usability:** Setup in under 30 minutes following the README; digest readable in under two minutes.
- **NFR-PORT-01 Portability:** Everything runs via `docker compose`; the project runs end to end in demo mode with mock emails and no credentials.

## 12. Security & Privacy Requirements

**Secrets and repository hygiene**

- `.env`, OAuth credentials, tokens and any local database are in `.gitignore`; `.env.example` contains only placeholders.
- A pre-commit secret scanner (for example gitleaks) and CI check run on every commit.
- Only synthetic, anonymized fixtures in `tests/` and `docs/`; screenshots use demo data.

**Data minimization toward the LLM**

- Send the minimum: sender domain (not full address), subject and a truncated, redacted body excerpt. Never send attachments, full headers, recipients or raw HTML.
- Rules short-circuit known senders and newsletters so a large share of emails never reaches the LLM at all.
- The LLM provider must be configured with data retention and training opt-outs where available; a local-model adapter (for example Ollama) is the privacy-maximal option.

**Prompt injection and malicious content**

- Email content is untrusted data. It is always passed as clearly delimited data in the user turn, never concatenated into system instructions.
- The LLM has **no tools and no side effects**; its only output is a JSON object that is schema-validated. A hijacked model can at worst produce a wrong label, never an action.
- Output constraints: enumerated categories, priorities and action types; bounded string lengths; links and HTML stripped from summaries.
- Safety-critical decisions (for example downgrading a sender to LOW) are never made by the LLM alone; sender-based rules take precedence.
- A test corpus of injection attempts ("ignore previous instructions", hidden text, fake system messages, instructions in other languages) lives in `tests/` and runs in CI.
- The digest is rendered with escaping so that crafted content cannot inject HTML or phishing links.

**Storage and retention**

- Stored by default: provider message ID, received timestamp, sender domain, category, priority, action type and deadline, short summary, processing status and whether the LLM was used.
- **Not stored:** full bodies, attachments, full recipient lists, raw headers. A debug mode that stores bodies must be opt-in, local-only and time-limited.
- Retention default 30 days, enforced by a scheduled cleanup; a `purge` command deletes everything.
- Database and token storage use disk encryption or an encrypted volume; OAuth tokens are encrypted at rest.

**Logging**

- Log IDs, counts, durations and error classes only; no subjects, bodies or addresses.

**GDPR considerations** (the user processes their own data, which is largely a household exemption, but the project should demonstrate the practices): data minimization, purpose limitation, storage limitation, right to erasure via `purge`, and a documented data-flow description including the third-country transfer risk when using a US-based LLM provider. Third-party senders' personal data in emails is a reason to prefer redaction and minimal storage.

**OAuth specifics:** Gmail scope `gmail.readonly`. Note that a Google Cloud project in "Testing" status issues refresh tokens that expire after 7 days; the setup guide must cover this limitation and the options (publishing the app in "production" for personal use, or re-authorizing).

## 13. MVP Definition

**MVP includes**

1. Gmail integration with read-only OAuth2.
2. Retrieval of new emails since the last run, with idempotent processing.
3. Preprocessing and redaction.
4. Rule-based categorization and priority hints (configurable in YAML).
5. LLM analysis for unresolved or relevant emails: category, priority, action items, short summary — schema-validated with rule-based fallback.
6. Daily digest rendered as HTML and plain text, delivered to the user's own address at the configured time.
7. Configuration file and `.env` handling with validation.
8. Structured logging and a basic run report.
9. Retention cleanup and purge command.
10. Tests with mocked emails, including prompt-injection cases; README and ADRs.

**MVP excludes:** immediate alerts, web UI, feedback learning, attachments, multiple providers, multi-user.

**Definition of done for the MVP:** `docker compose up` in demo mode produces a sample digest from synthetic emails; with real credentials it produces the user's real digest; all tests and CI checks pass; no secret or personal data is in the Git history.

## 14. Architecture Options

**Option A — Gmail → n8n → LLM → Email** Everything lives in n8n workflows.

- Advantages: fastest to build, minimal infrastructure, built-in Gmail OAuth and scheduling.
- Disadvantages: logic is hard to unit test and review in Git (large JSON workflows); prompt-injection defenses, redaction and schema validation become scattered code nodes; limited observability; weak as an engineering portfolio since it mostly shows configuration, not software design.

**Option B — Gmail → n8n → Backend API → AI → Database → n8n → Email** n8n is the thin orchestration layer (triggers, Gmail connector, scheduling, delivery); a backend service owns the pipeline and data.

- Advantages: core logic is real, testable, typed code; clear separation of concerns; n8n's OAuth handling and scheduling are reused; easy to demonstrate testing, security and architecture; the backend can later be driven by something other than n8n.
- Disadvantages: two components to run and document; a small HTTP contract between them must be maintained; some duplication of responsibility if boundaries are blurred.

**Option C — Gmail → Backend → AI → Database → Scheduler → Digest** A fully custom application with no n8n.

- Advantages: single codebase, maximum control, fewest moving parts at runtime, easiest to test end to end.
- Disadvantages: more upfront work (Gmail OAuth flow, scheduler, retries, mail delivery all hand-built); does not use the automation tooling you want to show; slower to reach a working MVP.

## 15. Recommended Architecture

**Recommendation: Option B, kept deliberately lean.**

- **n8n** does only what it is good at: a schedule trigger, fetching emails through the Gmail node, calling the backend over HTTP, and sending the finished digest. Exported workflows are versioned in `n8n/workflows/` (with credentials excluded).
- **Backend (Python, FastAPI)** owns preprocessing, redaction, rules, LLM adapter, output validation, persistence and digest rendering. Endpoints for the MVP are roughly `POST /emails/process` (batch) and `POST /digests` (generate for a period), plus a CLI for `purge` and a demo run.
- **Database:** SQLite for the MVP (single user, zero setup, file in a Docker volume), accessed through a repository layer so PostgreSQL remains an easy upgrade.
- **LLM adapter:** a small interface with one cloud implementation and, later, a local one.

**Why not Option A?** It would be done in a weekend but hides the interesting engineering. **Why not Option C?** It re-implements what n8n already solves and is the larger risk to finishing the MVP. Option B is the best trade-off between speed, demonstrable engineering and fit to your stack. A pragmatic path: build a throwaway Option A spike first (one day) to validate prompts and the digest format, then move the logic into the backend.

**Pipeline inside the backend**

Email → normalize → redact → rule engine → (confident? store) → LLM analysis with minimal payload → schema validation → fallback if invalid → store record → digest generator → rendered digest.

**Data flow summary**

1. Scheduler (n8n) triggers hourly or on a poll.
2. Gmail node returns new messages; n8n forwards a reduced payload to the backend.
3. Backend processes each email, stores metadata only, returns results.
4. At digest time, n8n calls `POST /digests`; the backend aggregates records and renders the digest.
5. n8n delivers the digest to the user's address.

## 16. Technology Recommendations

- **Language/framework:** Python 3.12, FastAPI, Pydantic (schemas, config validation and LLM output validation in one tool). This also matches your existing Python and REST experience.
- **Orchestration:** n8n (self-hosted via Docker).
- **Storage:** SQLite via SQLAlchemy, migrations with Alembic.
- **LLM:** a small, inexpensive model from a hosted provider using structured/JSON output; adapter pattern; optional local model later.
- **Testing:** pytest, pytest-cov, `respx` or `responses` for HTTP mocking, recorded synthetic fixtures.
- **Quality:** ruff, mypy, pre-commit, gitleaks, GitHub Actions CI.
- **Packaging:** Docker and docker compose (n8n + backend + volume).
- **Docs:** Markdown, Mermaid diagrams in the repo, ADRs in `docs/decisions/`.

Python versus Node.js: both fit your background; Python is recommended for Pydantic, the testing ecosystem and the LLM tooling, but this is a low-stakes choice and can be reversed in an ADR.

## 17. Risks

- **R1 Prompt injection** — mitigated by no-tool LLM, strict schema, data/instruction separation, injection test corpus.
- **R2 Privacy leakage to the LLM provider** — mitigated by redaction, minimization, rules-first, provider opt-outs, local-model option.
- **R3 Wrong classification or missed urgent email** — mitigated by conservative defaults (when uncertain, raise priority), sender allowlists for urgent senders, and a digest health section; the system is a convenience layer, not a replacement for the inbox.
- **R4 Hallucinated summaries or deadlines** — mitigated by short extractive-style prompts, required evidence fields in output, and displaying the original subject and sender next to each summary.
- **R5 Google OAuth friction** — 7-day refresh-token expiry in testing mode, verification requirements for sensitive scopes; mitigated by clear setup docs.
- **R6 Cost creep** — mitigated by rule short-circuiting, truncation, token budget.
- **R7 Scope creep / over-engineering** — mitigated by a strict MVP definition and phase gates.
- **R8 Accidental commit of secrets or real emails** — mitigated by `.gitignore`, pre-commit and CI scanning, synthetic fixtures only.
- **R9 n8n and backend boundary blur** — mitigated by an explicit HTTP contract documented in an ADR.

## 18. Open Questions

These need your decision before the architecture phase is finalized:

1. **LLM provider:** hosted API (cheaper to start, privacy trade-off) or local model (private, but needs hardware and tends to be weaker)? Do you have a preferred provider or an existing API key?
2. **Digest language:** German, English or configurable? Emails will likely be mixed-language.
3. **Hosting:** run on your laptop, a home server, or a small cloud VM (AWS would fit your experience)? This affects scheduling reliability and secret handling.
4. **Gmail setup:** one personal Gmail account? Are you willing to run your own Google Cloud OAuth project in production mode for personal use?
5. **Digest delivery:** email to yourself is assumed. Would you also like Telegram, Slack or similar later?
6. **Storage policy:** is metadata-only storage (no bodies) acceptable, even if it limits later features such as history search?
7. **Backend language:** are you happy with Python/FastAPI, or do you prefer Node.js?
8. **Digest time and window:** a fixed morning time covering the previous 24 hours, or also an evening digest?
9. **Portfolio presentation:** do you want a short demo GIF and a hosted read-only demo, or only the repository?

## 19. Proposed GitHub Repository Structure

```
ai-email-digest/
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── .pre-commit-config.yaml
├── docker-compose.yml
├── config/
│   ├── config.example.yaml        # categories, rules, digest time, retention
│   └── rules.example.yaml
├── docs/
│   ├── requirements.md
│   ├── use-cases.md
│   ├── architecture.md
│   ├── data-model.md
│   ├── security.md
│   ├── privacy-and-gdpr.md
│   └── decisions/                 # ADR-0001 ...
├── n8n/
│   └── workflows/                 # exported, credentials removed
├── src/
│   └── digest/
│       ├── api/                   # FastAPI routes
│       ├── providers/             # mail provider interface + Gmail mapping
│       ├── preprocessing/         # normalization, redaction
│       ├── rules/                 # deterministic rule engine
│       ├── llm/                   # adapter interface + implementations
│       ├── pipeline/              # orchestration of processing steps
│       ├── digest/                # aggregation and rendering
│       ├── storage/               # models, repositories, retention
│       └── config/                # settings and validation
├── prompts/                       # versioned prompt templates
├── tests/
│   ├── fixtures/                  # synthetic emails only
│   ├── unit/
│   ├── integration/
│   └── security/                  # prompt-injection corpus
├── docker/
│   ├── backend.Dockerfile
│   └── ...
└── .github/
    └── workflows/ci.yml
```

This will be adjusted once the architecture is confirmed.

## 20. Development Roadmap

- **Phase 1 — Requirements:** this document. Gate: your approval and answers to the open questions.
- **Phase 2 — Use-case diagram:** final actors and use cases, with a Mermaid diagram.
- **Phase 3 — Architecture:** component diagram, data flow, data model, trust boundaries and threat model; ADR-0001 (architecture choice).
- **Phase 4 — Technology decisions:** confirm stack and LLM provider; ADRs for storage, LLM adapter and language.
- **Phase 5 — Repository setup:** structure, tooling, CI, pre-commit secret scanning, Docker skeleton, `.env.example`.
- **Phase 6 — MVP implementation:** in small vertical slices: (1) demo-mode pipeline with mock emails, (2) rules and preprocessing, (3) LLM adapter with validation, (4) persistence and retention, (5) digest rendering, (6) n8n workflows and Gmail integration.
- **Phase 7 — Testing:** unit, integration, failure-mode and prompt-injection tests; coverage target.
- **Phase 8 — Security review:** threat model review, dependency and secret scanning, log review, privacy walkthrough.
- **Phase 9 — Documentation:** README, setup guides (Gmail, n8n, LLM), screenshots with demo data, limitations.
- **Phase 10 — Deployment:** hardened Docker setup, scheduling, backups, monitoring of run reports.
- **Phase 11 — Advanced features:** immediate alerts, history UI, feedback learning, additional providers, local LLM.

After each phase I will summarize what was completed and what comes next, and I will wait for your approval before continuing.

---

**Next step:** please review this document and answer the open questions in section 18 (even brief answers are fine). Once you approve, I will move to Phase 2 (use-case model and diagram).
