"""Read-only data access for admin screens.

Admin is itself a slice, so it touches models directly rather than reaching
into other slices' internals. Write-side helpers (issue toggle/approve/send)
live in dedicated services beside the routes that need them.

``NewsletterIssue.candidate_ids_json`` schema accepted by the parsers below::

    {"expert":    [{"id": 1, "included": true}, ...],
     "practical": [{"id": 4, "included": true}, ...]}

Legacy plain-int lists (``{"expert": [1, 2, 3]}``) are still accepted for
back-compat with anything that emits the simpler form; entries default
to ``included=true``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.models.source import Source

TRACK_KEYS = ("expert", "practical")


@dataclass(slots=True, frozen=True)
class DashboardStats:
    collected_today: int
    processed_today: int
    candidates_count: int
    pending_review: int


@dataclass(slots=True, frozen=True)
class IssueRow:
    id: int
    issue_date: date
    title: str
    status: str
    expert_count: int
    practical_count: int


# Back-compat alias — dashboard.html and existing tests still reference this name.
RecentIssue = IssueRow


@dataclass(slots=True, frozen=True)
class CandidateView:
    processed_item_id: int
    track: str
    title: str
    source_name: str
    category: str | None
    importance_score: float
    url: str
    included: bool


@dataclass(slots=True, frozen=True)
class IssueDetail:
    issue: NewsletterIssue
    expert_candidates: list[CandidateView]
    practical_candidates: list[CandidateView]


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
    candidates = _candidate_included_total_for(session, today)

    return DashboardStats(
        collected_today=collected,
        processed_today=processed,
        candidates_count=candidates,
        pending_review=pending,
    )


def list_issues(
    session: Session,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[IssueRow]:
    stmt = select(NewsletterIssue)
    if status:
        stmt = stmt.where(NewsletterIssue.status == status)
    stmt = stmt.order_by(NewsletterIssue.issue_date.desc(), NewsletterIssue.id.desc()).limit(limit)
    return [_to_row(issue) for issue in session.scalars(stmt).all()]


def list_recent_issues(session: Session, limit: int = 10) -> list[IssueRow]:
    return list_issues(session, limit=limit)


def get_issue_detail(session: Session, issue_id: int) -> IssueDetail | None:
    issue = session.get(NewsletterIssue, issue_id)
    if issue is None:
        return None

    expert_entries = _entries_for_track(issue.candidate_ids_json, "expert")
    practical_entries = _entries_for_track(issue.candidate_ids_json, "practical")

    all_ids = [pid for pid, _ in expert_entries] + [pid for pid, _ in practical_entries]
    items_by_id = _fetch_processed_context(session, all_ids)

    def _resolve(entries: list[tuple[int, bool]], track: str) -> list[CandidateView]:
        out: list[CandidateView] = []
        for pid, included in entries:
            info = items_by_id.get(pid)
            if info is None:
                continue
            out.append(
                CandidateView(
                    processed_item_id=pid,
                    track=track,
                    title=info["title"],
                    source_name=info["source_name"],
                    category=info["category"],
                    importance_score=info["importance_score"],
                    url=info["url"],
                    included=included,
                )
            )
        return out

    return IssueDetail(
        issue=issue,
        expert_candidates=_resolve(expert_entries, "expert"),
        practical_candidates=_resolve(practical_entries, "practical"),
    )


# ---------- internal helpers ------------------------------------------------


def _to_row(issue: NewsletterIssue) -> IssueRow:
    expert, practical = _split_candidate_counts(issue.candidate_ids_json)
    return IssueRow(
        id=issue.id,
        issue_date=issue.issue_date,
        title=issue.title,
        status=issue.status,
        expert_count=expert,
        practical_count=practical,
    )


def _candidate_included_total_for(session: Session, today: date) -> int:
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
    data = _parse_candidate_blob(raw)
    return (
        _count_included(data.get("expert")),
        _count_included(data.get("practical")),
    )


def _count_included(arr: Any) -> int:
    if not isinstance(arr, list):
        return 0
    total = 0
    for entry in arr:
        if isinstance(entry, dict):
            if entry.get("included", True):
                total += 1
        elif isinstance(entry, int):
            total += 1
    return total


def _entries_for_track(raw: str | None, track: str) -> list[tuple[int, bool]]:
    data = _parse_candidate_blob(raw)
    arr = data.get(track)
    if not isinstance(arr, list):
        return []
    out: list[tuple[int, bool]] = []
    for entry in arr:
        if isinstance(entry, dict):
            pid = entry.get("id")
            if isinstance(pid, int):
                out.append((pid, bool(entry.get("included", True))))
        elif isinstance(entry, int):
            out.append((entry, True))
    return out


def _parse_candidate_blob(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _fetch_processed_context(session: Session, ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    stmt = (
        select(ProcessedItem, RawItem, Source)
        .join(RawItem, RawItem.id == ProcessedItem.raw_item_id)
        .join(Source, Source.source_id == RawItem.source_id, isouter=True)
        .where(ProcessedItem.id.in_(ids))
    )
    out: dict[int, dict[str, Any]] = {}
    for proc, raw, source in session.execute(stmt).all():
        out[proc.id] = {
            "title": proc.normalized_title,
            "category": proc.category,
            "importance_score": proc.importance_score,
            "url": raw.url if raw else "",
            "source_name": source.name if source else "(unknown)",
        }
    return out
