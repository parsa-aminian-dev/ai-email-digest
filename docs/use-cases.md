# MVP use cases

```mermaid
flowchart LR
    User[Mailbox owner] --> Configure[Edit validated configuration]
    User --> Read[Read delivered digest]
    User --> Purge[Delete local data with CLI]
    Scheduler[n8n / built-in scheduler] --> Poll[Ingest new messages]
    Poll --> Process[Normalize, apply rules and analyze selectively]
    Gmail[Gmail read-only API] --> Poll
    Process --> Store[Store minimized metadata]
    Scheduler --> Generate[Generate due digest]
    Store --> Generate
    Generate --> Deliver[Send digest to fixed owner]
    Deliver --> Read
```

Failures in a message or external analysis fall back to independent processing and are surfaced in health counts. A Gmail outage leaves the checkpoint intact and still permits a degraded digest. History metadata can be inspected through `GET /items`; feedback learning, immediate alerts and a history UI remain post-MVP.
