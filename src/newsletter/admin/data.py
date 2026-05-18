"""Read-only data access for admin screens.

Admin is itself a slice, so it touches models directly rather than reaching
into other slices' internals. Write-side helpers (issue toggle/approve/send)
live in dedicated services beside the routes that need them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem


@dataclass(slots=True, frozen=True)
class DashboardStats:
    collected_today: int
    processed_today: int
    candidates_count: int
    pending_review: int


@dataclass(slots=True, frozen=True)
class RecentIssue:
    id: int
    issue_date: date
    title: str
    status: str
    expert_count: int
    practical_count: int


def get_dashboard_stats(session: Session, today: date) -> DashboardStats:
    start = datetime.combine(today, time.min, tzinfo=UTC)
    end = datetime.combine(today, time.max, tzinfo=UTC)

    collected = (
        session.scalar(
            select(func.count(RawItem.id)).where(
                RawItem.collected_at >= start,
                RawItem.collected_at <= end,
            )
        )
        or 0
    )
    processed = (
        session.scalar(
            select(func.count(ProcessedItem.id)).where(
                ProcessedItem.created_at >= start,
                ProcessedItem.created_at <= end,
            )
        )
        or 0
    )
    pending = (
        session.scalar(
            select(func.count(NewsletterIssue.id)).where(
                NewsletterIssue.status == "review_required",
            )
        )
        or 0
    )
    candidates = _candidate_total_for(session, today)

    return DashboardStats(
        collected_today=collected,
        processed_today=processed,
        candidates_count=candidates,
        pending_review=pending,
    )


def list_recent_issues(session: Session, limit: int = 10) -> list[RecentIssue]:
    rows = session.scalars(
        select(NewsletterIssue)
        .order_by(NewsletterIssue.issue_date.desc(), NewsletterIssue.id.desc())
        .limit(limit)
    ).all()
    out: list[RecentIssue] = []
    for issue in rows:
        expert, practical = _split_candidate_counts(issue.candidate_ids_json)
        out.append(
            RecentIssue(
                id=issue.id,
                issue_date=issue.issue_date,
                title=issue.title,
                status=issue.status,
                expert_count=expert,
                practical_count=practical,
            )
        )
    return out


def _candidate_total_for(session: Session, today: date) -> int:
    issue = session.scalar(
        select(NewsletterIssue)
        .where(NewsletterIssue.issue_date == today)
        .order_by(NewsletterIssue.id.desc())
        .limit(1)
    )
    if issue is None:
        return 0
    expert, practical = _split_candidate_counts(issue.candidate_ids_json)
    return expert + practical


def _split_candidate_counts(raw: str | None) -> tuple[int, int]:
    if not raw:
        return 0, 0
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return 0, 0
    if not isinstance(data, dict):
        return 0, 0
    expert = data.get("expert")
    practical = data.get("practical")
    return (
        len(expert) if isinstance(expert, list) else 0,
        len(practical) if isinstance(practical, list) else 0,
    )
