"""SMTP sender — thin wrapper around stdlib smtplib + email.message.

The wrapper exists so tests can inject a fake ``SenderProtocol`` instead
of hitting smtplib (or worse, a real SMTP server).
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from newsletter.core.config import Settings
from newsletter.core.logging import get_logger

log = get_logger(__name__)

_SMTP_TIMEOUT_SECONDS = 30


@dataclass(slots=True, frozen=True)
class Mail:
    """A composed message ready to hand to a ``SenderProtocol``."""

    sender: str
    recipients: tuple[str, ...]
    subject: str
    plain_body: str
    html_body: str | None = None


class SenderProtocol(Protocol):
    def send(self, mail: Mail) -> None: ...


class SMTPSender:
    """Connects per call — short-lived, easy to reason about for nightly use."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        use_starttls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_starttls = use_starttls

    @classmethod
    def from_settings(cls, settings: Settings) -> SMTPSender:
        return cls(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
        )

    def send(self, mail: Mail) -> None:
        msg = EmailMessage()
        msg["From"] = mail.sender
        msg["To"] = ", ".join(mail.recipients)
        msg["Subject"] = mail.subject
        msg.set_content(mail.plain_body)
        if mail.html_body:
            msg.add_alternative(mail.html_body, subtype="html")

        with smtplib.SMTP(self.host, self.port, timeout=_SMTP_TIMEOUT_SECONDS) as smtp:
            if self.use_starttls:
                smtp.starttls()
            smtp.login(self.user, self.password)
            smtp.send_message(msg)
        log.info(
            "distribution.smtp.sent",
            host=self.host,
            port=self.port,
            recipients=len(mail.recipients),
        )


__all__ = ["Mail", "SMTPSender", "SenderProtocol"]
