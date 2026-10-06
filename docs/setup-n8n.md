# n8n orchestration

n8n triggers the backend and sees only a run report and digest ID. Mailbox access, AI analysis, digest rendering, and SMTP delivery stay in the backend so retries, privacy controls, and delivery receipts have one owner. The exported workflow contains no credentials or email bodies.

1. Generate a random `API_KEY` and `N8N_ENCRYPTION_KEY` in the private `.env`. Set `SCHEDULER_ENABLED=false` to select n8n as the scheduler.
2. Start `docker compose --profile automation up --build --detach --wait`.
3. Open `http://localhost:5678`, create your n8n owner account, and import `n8n/workflows/daily-digest.json` through **Import from file**.
4. Create a **Header Auth** credential with header name `X-API-Key` and your backend API key. Select that credential in **Ingest and deliver due digest**. Credentials are stored only in your private n8n volume, encrypted with the configured encryption key.
5. Set the workflow time zone to match the digest configuration, manually test it, and publish/activate it. The workflow is deliberately inactive in the exported file.
6. It calls `POST http://backend:8000/jobs/tick` every five minutes. The backend polls messages and selects the scheduled daily boundary from YAML, so changing the digest time does not require rewriting the workflow.

Only the backend and n8n container network use the `backend` hostname. A locally run n8n instance uses `http://localhost:8000` instead. The built-in scheduler can be used without n8n, but choose one scheduler to avoid unnecessary polling.

Successful and failed n8n execution payload storage is disabled both in Compose and the workflow. Protect the n8n UI with its owner account; it is bound to localhost. Back up the encryption key alongside the encrypted volume, separately from source control.

See the official [Schedule Trigger documentation](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger). Live Gmail credentials and SMTP delivery should be tested by the mailbox owner after setup.
