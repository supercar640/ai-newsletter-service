"""Archive NewsletterIssue rows to Notion.

Two entry points:

* :func:`archive_issue` — one issue, one Notion page. Refuses to re-archive
  an issue that already has a ``notion_page_id`` unless ``force=True``.
* :func:`backfill_archive` — every ``status='sent'`` row whose
  ``notion_page_id`` is null. Per-issue failures are captured in the
  report so a single flaky call doesn't abort the whole batch.

The service treats a missing Notion client as configuration absence, not
an error in the system — callers raise :class:`ArchiveDisabledError` to
the user with a helpful message rather than dropping requests silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.core.logging import get_logger
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.archive.markdown_blocks import markdown_to_blocks
from newsletter.slices.archive.notion_client import NotionError

log = get_logger(__name__)


class ArchiveDisabledError(Exception):
    """Raised when the caller tries to archive without Notion configured."""


class AlreadyArchivedError(Exception):
    """Raised when an issue already has a ``notion_page_id`` and ``force`` is false."""


class _NotionTarget(Protocol):
    """Subset of NotionClient used by the service (keeps tests light)."""

    database_id: str

    def create_page(
        self,
        *,
        title: str,
        properties: dict,
        children: list,
    ) -> str: ...


@dataclass(slots=True, frozen=True)
class ArchiveReport:
    """Outcome of a single ``archive_issue`` call."""

    issue_id: int
    page_id: str
    forced: bool = False


@dataclass
class BackfillReport:
    """Outcome of a backfill run."""

    archived_count: int = 0
    skipped_count: int = 0
    errors: list[tuple[int, str]] = field(default_factory=list)


def archive_issue(
    session: Session,
    issue: NewsletterIssue,
    *,
    client: _NotionTarget | None,
    force: bool = False,
) -> ArchiveReport:
    """Create one Notion page from an issue. Idempotent unless ``force``."""
    if client is None:
        raise ArchiveDisabledError(
            "Notion 통합이 설정되지 않았습니다. NOTION_TOKEN / NOTION_DATABASE_ID 를 확인해주세요."
        )
    if issue.notion_page_id and not force:
        raise AlreadyArchivedError(
            f"issue {issue.id} 는 이미 아카이브되어 있습니다 (page_id={issue.notion_page_id})."
        )

    properties = _build_properties(issue)
    children = markdown_to_blocks(issue.markdown_body or "")
    page_id = client.create_page(
        title=issue.title,
        properties=properties,
        children=children,
    )
    issue.notion_page_id = page_id
    issue.archived_at = datetime.now(UTC)
    session.flush()
    log.info(
        "archive.notion.created",
        issue_id=issue.id,
        page_id=page_id,
        forced=force,
    )
    return ArchiveReport(issue_id=issue.id, page_id=page_id, forced=force)


def backfill_archive(session: Session, *, client: _NotionTarget | None) -> BackfillReport:
    """Archive every ``sent`` issue that still lacks a notion_page_id.

    Errors per issue are captured rather than raised so the operator can
    inspect what failed in one pass.
    """
    if client is None:
        raise ArchiveDisabledError(
            "Notion 통합이 설정되지 않았습니다. NOTION_TOKEN / NOTION_DATABASE_ID 를 확인해주세요."
        )

    report = BackfillReport()
    rows = list(
        session.scalars(
            select(NewsletterIssue)
            .where(NewsletterIssue.status == "sent")
            .order_by(NewsletterIssue.id)
        ).all()
    )
    for issue in rows:
        if issue.notion_page_id:
            report.skipped_count += 1
            continue
        try:
            archive_issue(session, issue, client=client)
            report.archived_count += 1
        except NotionError as exc:
            report.errors.append((issue.id, f"NotionError: {exc}"))
            log.warning("archive.notion.failed", issue_id=issue.id, error=str(exc))
        except Exception as exc:
            report.errors.append((issue.id, f"{type(exc).__name__}: {exc}"))
            log.exception("archive.notion.unexpected", issue_id=issue.id)
    return report


def _build_properties(issue: NewsletterIssue) -> dict:
    """Notion-properties payload (sans ``Name`` — the client adds it)."""
    audience = issue.audience or "general"
    props: dict = {
        "Date": {"date": {"start": issue.issue_date.isoformat()}},
        "Audience": {"select": {"name": audience}},
        "Status": {"select": {"name": issue.status}},
    }
    return props


__all__ = [
    "AlreadyArchivedError",
    "ArchiveDisabledError",
    "ArchiveReport",
    "BackfillReport",
    "NotionError",
    "archive_issue",
    "backfill_archive",
]
