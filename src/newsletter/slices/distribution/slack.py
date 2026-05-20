"""Post a NewsletterIssue to Slack as a summary card.

State machine guard (spec §9.2 / AGENTS.md): ``approved`` is the only status
from which an issue may be distributed. Slack is an independent channel — it
does NOT transition ``status`` (email send owns the ``sent`` transition); it
only stamps ``slack_sent_at``. Re-posting is refused unless ``force=True``,
mirroring the archive slice's idempotency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from newsletter.core.logging import get_logger
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.distribution.card import build_card

log = get_logger(__name__)


class SlackSendError(Exception):
    """Raised when the issue cannot be posted (state guard)."""


class SlackDisabledError(Exception):
    """Raised when posting is attempted without Slack configured."""


class AlreadySentError(Exception):
    """Raised when ``slack_sent_at`` is already set and ``force`` is false."""


class _SlackTarget(Protocol):
    def post(self, blocks: list[dict]) -> None: ...


@dataclass(slots=True, frozen=True)
class SlackReport:
    dry_run: bool
    posted_at: datetime | None


def post_issue_to_slack(
    session: Session,
    issue: NewsletterIssue,
    *,
    client: _SlackTarget | None,
    dry_run: bool = False,
    force: bool = False,
    now: datetime | None = None,
) -> SlackReport:
    """Post ``issue`` to Slack (or simulate it under dry-run)."""
    if client is None:
        raise SlackDisabledError(
            "Slack 통합이 설정되지 않았습니다. SLACK_WEBHOOK_URL 을 확인해주세요."
        )
    if issue.status != "approved":
        raise SlackSendError(
            f"발송 불가: 이슈 상태가 {issue.status} 입니다. approved 상태에서만 발송할 수 있습니다."
        )
    if issue.slack_sent_at and not force:
        raise AlreadySentError(
            f"issue {issue.id} 는 이미 Slack 으로 발송되었습니다 "
            f"(slack_sent_at={issue.slack_sent_at.isoformat()})."
        )

    blocks = build_card(issue)

    if dry_run:
        log.info("distribution.slack.dry_run", issue_id=issue.id, blocks=len(blocks))
        return SlackReport(dry_run=True, posted_at=None)

    client.post(blocks)

    posted_at = now or datetime.now(UTC)
    issue.slack_sent_at = posted_at
    session.flush()

    log.info(
        "distribution.slack.posted",
        issue_id=issue.id,
        posted_at=posted_at.isoformat(),
    )
    return SlackReport(dry_run=False, posted_at=posted_at)


__all__ = [
    "AlreadySentError",
    "SlackDisabledError",
    "SlackReport",
    "SlackSendError",
    "post_issue_to_slack",
]
