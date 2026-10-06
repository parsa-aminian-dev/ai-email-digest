from datetime import UTC, datetime, timedelta

from src.digest.models import EmailMessage


def demo_emails(now: datetime | None = None) -> list[EmailMessage]:
    now = now or datetime.now(UTC)
    examples = [
        (
            "billing@payments.example",
            "Invoice due today",
            "Your invoice is due today. Please pay by 2026-10-07.",
        ),
        (
            "news@weekly.example",
            "Weekly newsletter",
            "This week in science. Unsubscribe at https://weekly.example.",
        ),
        (
            "team@company.example",
            "Shift changed: please confirm",
            "Your shift now starts at 10:00. Please confirm.",
        ),
        (
            "security@account.example",
            "Suspicious login detected",
            "Unauthorized access detected. Change your password.",
        ),
        (
            "shipping@shop.example",
            "Delivery needs a signature",
            "Your delivery arrives tomorrow. Please attend.",
        ),
        ("friend@personal.example", "Dinner on Friday", "Join us for dinner on Friday evening."),
        ("unknown@example.org", "A quick question", "Please reply when you have a moment."),
    ]
    return [
        EmailMessage(
            id=f"demo-{now.date()}-{i}",
            sender=sender,
            subject=subject,
            body=body,
            received_at=now - timedelta(hours=i + 1),
            labels=["INBOX"],
            metadata={"list_unsubscribe": i == 1},
        )
        for i, (sender, subject, body) in enumerate(examples)
    ]
