"""Competitor mention analysis over accumulated ProcessedItem rows.

The service is the only place that touches the DB. It resolves a single
look-back window, anchors each item by published_at (falling back to
created_at), runs deterministic alias matching, and rolls the matches up
into a CompetitorReport. No LLM, no embeddings.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.competitors import repository
from newsletter.slices.competitors.matching import (
    CompetitorProfile,
    mentioned_competitor_ids,
)
from newsletter.slices.competitors.schemas import (
    CompetitorMentions,
    CompetitorReport,
    Headline,
)


def analyze_competitors(
    session: Session,
    *,
    days: int = 7,
    until: date | None = None,
    since: date | None = None,
    top_k: int = 5,
) -> CompetitorReport:
    """Build a CompetitorReport over a single look-back window.

    Window is half-open ``[since, until)``. ``until`` defaults to tomorrow
    (so today is included); ``since`` defaults to ``until - days`` but an
    explicit ``since`` wins. Each enabled competitor is included even with a
    zero count (watch-list semantics).
    """
    until_date = until or (date.today() + timedelta(days=1))
    since_date = since or (until_date - timedelta(days=days))
    lo = datetime.combine(since_date, time.min)
    hi = datetime.combine(until_date, time.min)

    profiles = _load_profiles(session)
    # name + zero-count seed for every enabled competitor (watch-list)
    counts: dict[int, int] = {p.id: 0 for p in profiles}
    headlines: dict[int, list[Headline]] = {p.id: [] for p in profiles}
    names: dict[int, str] = {p.id: p.name for p in profiles}

    total_items = 0
    for title, summary, url, importance, published_at, created_at in _fetch(session, lo, hi):
        anchor = _anchor(published_at, created_at)
        # _fetch already window-filters in SQL, but re-check after _anchor
        # normalizes tz-aware timestamps to naive UTC (a tz-aware published_at
        # can pass the naive SQL bound yet fall outside the window once shifted).
        if anchor is None or not (lo <= anchor < hi):
            continue
        total_items += 1
        text_lower = f"{title or ''} {summary or ''}".lower()
        for cid in mentioned_competitor_ids(text_lower, profiles):
            counts[cid] += 1
            headlines[cid].append(Headline(title=title, url=url, importance=importance or 0.0))

    mentions = [
        CompetitorMentions(
            name=names[cid],
            count=counts[cid],
            headlines=sorted(headlines[cid], key=lambda h: h.importance, reverse=True)[:top_k],
        )
        for cid in counts
    ]
    mentions.sort(key=lambda m: (-m.count, m.name))

    return CompetitorReport(
        since=since_date,
        until=until_date,
        total_items=total_items,
        competitors=mentions,
    )


def _load_profiles(session: Session) -> list[CompetitorProfile]:
    rows = repository.list_competitors(session, only_enabled=True)
    return [
        CompetitorProfile(
            id=row.id,
            name=row.name,
            aliases=tuple(a.lower() for a in repository.load_aliases(row)),
        )
        for row in rows
    ]


def _fetch(session: Session, lo: datetime, hi: datetime):
    """Rows whose anchor (published_at, else created_at) falls in [lo, hi)."""
    stmt = (
        select(
            ProcessedItem.normalized_title,
            ProcessedItem.summary,
            ProcessedItem.canonical_url,
            ProcessedItem.importance_score,
            RawItem.published_at,
            ProcessedItem.created_at,
        )
        .join(RawItem, RawItem.id == ProcessedItem.raw_item_id)
        .where(
            or_(
                and_(
                    RawItem.published_at.is_not(None),
                    RawItem.published_at >= lo,
                    RawItem.published_at < hi,
                ),
                and_(
                    RawItem.published_at.is_(None),
                    ProcessedItem.created_at >= lo,
                    ProcessedItem.created_at < hi,
                ),
            )
        )
    )
    return session.execute(stmt).all()


def _anchor(published_at: datetime | None, created_at: datetime | None) -> datetime | None:
    """Pick published_at else created_at, normalized to naive UTC for comparison."""
    dt = published_at if published_at is not None else created_at
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


__all__ = ["analyze_competitors"]
