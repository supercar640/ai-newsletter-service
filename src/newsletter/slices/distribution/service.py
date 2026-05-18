"""Send a NewsletterIssue.

State machine guard (spec §9.2 / AGENTS.md):
``approved`` is the only status from which an issue can be sent. Any
other status raises :class:`SendError`. There is no ``--force``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from newsletter.core.config import Settings, get_settings
from newsletter.core.logging import get_logger
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.distribution.sender import Mail, SenderProtocol, SMTPSender

log = get_logger(__name__)


class SendError(Exception):
    """Raised when an issue cannot be sent for any reason."""


@dataclass(slots=True, frozen=True)
class SendReport:
    dry_run: bool
    recipients: tuple[str, ...]
    sent_at: datetime | None


def send_issue(
    session: Session,
    issue: NewsletterIssue,
    *,
    sender: SenderProtocol | None = None,
    settings: Settings | None = None,
    dry_run: bool = True,
    now: datetime | None = None,
) -> SendReport:
    """Send ``issue`` via SMTP (or simulate it under dry-run).

    Side effects on the issue row (only when ``dry_run=False``):
      * ``status`` → ``"sent"``
      * ``sent_at`` → ``now`` (UTC)
    """
    if issue.status != "approved":
        raise SendError(
            f"발송 불가: 이슈 상태가 {issue.status} 입니다. approved 상태에서만 발송할 수 있습니다."
        )

    settings = settings or get_settings()
    recipients = tuple(settings.recipient_list)
    if not recipients:
        raise SendError("NEWSLETTER_RECIPIENTS 환경변수가 비어 있습니다.")

    sender_addr = settings.smtp_from or settings.smtp_user
    if not sender_addr:
        raise SendError("SMTP_FROM 또는 SMTP_USER가 설정되어 있지 않습니다.")

    if dry_run:
        log.info(
            "distribution.dry_run",
            issue_id=issue.id,
            recipients=len(recipients),
        )
        return SendReport(dry_run=True, recipients=recipients, sent_at=None)

    mail = Mail(
        sender=sender_addr,
        recipients=recipients,
        subject=issue.title,
        plain_body=_markdown_to_plain(issue.markdown_body or ""),
        html_body=issue.html_body,
    )

    smtp = sender or SMTPSender.from_settings(settings)
    smtp.send(mail)

    sent_at = now or datetime.now(UTC)
    issue.status = "sent"
    issue.sent_at = sent_at
    session.flush()

    log.info(
        "distribution.sent",
        issue_id=issue.id,
        recipients=len(recipients),
        sent_at=sent_at.isoformat(),
    )
    return SendReport(dry_run=False, recipients=recipients, sent_at=sent_at)


_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_MD_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_MD_HEAD = re.compile(r"^#{1,6}\s+", re.MULTILINE)


def _markdown_to_plain(markdown: str) -> str:
    """Best-effort plain-text view of the markdown for the text/plain alternative.

    Not a real renderer — we strip the few markers that look noisy when
    rendered as plain text and otherwise preserve content verbatim. The
    HTML alternative is the authoritative version.
    """
    text = _MD_LINK.sub(r"\1 (\2)", markdown)
    text = _MD_BOLD.sub(r"\1", text)
    text = _MD_ITALIC.sub(r"\1", text)
    text = _MD_HEAD.sub("", text)
    return text


__all__ = ["SendError", "SendReport", "send_issue"]
