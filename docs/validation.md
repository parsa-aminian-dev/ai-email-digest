# Local validation — 2026-10-06

- 65 pytest tests passed; 94.82% coverage of backend/core modules (CLI tested separately).
- Ruff lint and formatting passed. Mypy passed for all 30 source files.
- Runtime dependency consistency check passed. The pinned runtime list's pip-audit scan found no known vulnerabilities.
- Gitleaks scanned both existing Git history commits and the tracked/untracked project source snapshot: no secrets found.
- Docker Compose and pre-commit configurations validated. Hooks are configured for installation by the owner; no commit was created.
- A real local Uvicorn HTTP smoke check passed: seven synthetic messages, minimized metadata, action/deadline details and safe digest HTML.
- Gmail pagination/retry/checkpoint behavior, OpenAI schema/evidence validation and token budgets, TLS SMTP and ambiguous-delivery handling were verified with mocks. No real account or outbound delivery was tested.

Docker Desktop was started for an isolated container build. The image's dependency installation succeeded, but Docker failed to commit its layer with an I/O error in `/var/lib/docker/buildkit/metadata_v2.db`. Docker disk-usage inspection also returned an overlay storage I/O error. The host had approximately 164 MB free at diagnosis. No existing Docker volumes, caches or unrelated files were deleted to recover space. The container demo could not be verified on this host; CI includes that smoke test for a healthy runner.

The local credential-free preview was left running on port 8000 using `data/demo-preview.db`, separate from the default application database. Its generated files and database are ignored by Git. Stop that local server before binding Docker to the same port.
