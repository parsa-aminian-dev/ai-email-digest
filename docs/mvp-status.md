# MVP requirement mapping

| Requirements | Implementation / verification |
| --- | --- |
| FR-001–003 | Read-only Gmail REST adapter, incremental checkpoint/overlap, provider IDs; mocked pagination/retry tests |
| FR-005–007 | HTML/quote/signature normalization, bounded byte/character size, sensitive-pattern redaction; redaction tests |
| FR-008–011 | Validated sender/domain/subject/label/unsubscribe rules, configured categories/priorities, selective AI |
| FR-012–015 | Enumerated action/deadline extraction, structured AI validation, evidence grounding, rules fallback, no tools |
| FR-016 | Priority/category digest and optional AI overview; deterministic overview when AI disabled |
| FR-017 | Local-time daily windows, DST tests, n8n workflow and optional scheduler, TLS SMTP |
| FR-018–019 | Failure/fallback health metrics, escaped rendering with no remote links/images; security tests |
| FR-020–022 | Validated YAML/environment, SQLite retention, cleanup/purge CLI |
| NFR observability/quality | Structured metrics/logging, lint, types, core coverage gate, mocked integrations, pinned runtime dependencies, security scan and Docker smoke CI |
| Portfolio documentation | Requirements, architecture/use-case diagrams, data model, security/data flow, setup guides, ADRs |

Deliberate implementation choices are recorded in ADR-0002: standard-library SQLite rather than SQLAlchemy/Alembic, backend-owned Gmail/SMTP rather than mailbox content traversing n8n, and disabled AI by default. Regex minimization is not full anonymization; at-rest encryption requires an encrypted host/volume. Metadata includes redacted original subjects to make digest entries recognizable.

SMTP failure/crash ambiguity is reconciled manually and never blindly retried. A working real-mail deployment needs the owner's OAuth, SMTP and optional AI credentials. Mocked tests and the credential-free Docker demo cannot prove access to an unconfigured account. Cost/throughput depend on volume, network latency and provider settings; there is no €1/month guarantee.

Post-MVP FR-023–025 (immediate alerts, user correction and learning) remain outside this implementation, as defined in the approved task reference.
