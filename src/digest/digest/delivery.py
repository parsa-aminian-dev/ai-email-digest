from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from src.digest.config.settings import Settings
from src.digest.models import DigestResult


class Delivery:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate(self) -> None:
        if self.settings.demo_mode:
            return
        if (
            not self.settings.smtp_host
            or not self.settings.digest_from
            or not self.settings.digest_to
        ):
            raise ValueError("SMTP_HOST, DIGEST_FROM and DIGEST_TO are required")
        for address in (self.settings.digest_from, self.settings.digest_to):
            if "\r" in address or "\n" in address or "@" not in address:
                raise ValueError("Invalid digest delivery address")

    def send(self, result: DigestResult) -> None:
        self.validate()
        if self.settings.demo_mode:
            self.write_preview(result)
            return
        message = EmailMessage()
        message["Subject"] = (
            f"Email digest — {result.interval_end.date() if result.interval_end else result.generated_at.date()}"
        )
        message["From"] = self.settings.digest_from
        message["To"] = self.settings.digest_to
        message["Message-ID"] = f"<digest-{result.id}@ai-email-digest.local>"
        message.set_content(result.text)
        message.add_alternative(result.html, subtype="html")
        context = ssl.create_default_context()
        smtp: smtplib.SMTP
        if self.settings.smtp_security == "ssl":
            smtp = smtplib.SMTP_SSL(
                self.settings.smtp_host, self.settings.smtp_port, timeout=30, context=context
            )
        else:
            smtp = smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=30)
        with smtp:
            if self.settings.smtp_security == "starttls":
                smtp.starttls(context=context)
            if self.settings.smtp_user:
                smtp.login(self.settings.smtp_user, self.settings.smtp_password.get_secret_value())
            # Delivery is fixed to the configured owner, never an email-derived recipient.
            smtp.send_message(
                message, from_addr=self.settings.digest_from, to_addrs=[self.settings.digest_to]
            )

    def write_preview(self, result: DigestResult) -> None:
        directory = Path(self.settings.output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
        for suffix, content in (("html", result.html), ("txt", result.text)):
            path = directory / f"{result.id}.{suffix}"
            path.write_text(content, encoding="utf-8")
            path.chmod(0o600)
