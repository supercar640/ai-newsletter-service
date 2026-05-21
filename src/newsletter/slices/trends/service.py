"""Trend analysis over accumulated ProcessedItem rows.

The service is the only place that touches the DB. It resolves two equal-length
date windows (current vs previous), anchoring each item by published_at (falling
back to created_at), counts distinct title terms per article, and delegates the
classification to the pure ``compare_windows``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.trends.analysis import compare_windows
from newsletter.slices.trends.schemas import TrendReport, WindowSpec
from newsletter.slices.trends.terms import title_terms

_PERIOD_DAYS = {"week": 7, "month": 30}


def build_window_spec(period: str, end: date) -> WindowSpec:
    """Two equal-length windows ending on ``end`` (inclusive of end's date)."""
    if period not in _PERIOD_DAYS:
        raise ValueError(f"unknown period: {period!r} (expected week|month)")
    delta = timedelta(days=_PERIOD_DAYS[period])
    current_end = end + timedelta(days=1)  # exclusive upper bound
    current_start = current_end - delta
    previous_start = current_start - delta
    return WindowSpec(
        period=period,
        current_start=current_start,
        current_end=current_end,
        previous_start=previous_start,
        previous_end=current_start,
    )


def analyze_trends(
    session: Session,
    *,
    period: str = "week",
    end: date | None = None,
    top_n: int = 15,
    min_count: int = 2,
) -> TrendReport:
    """Build a TrendReport comparing the current window against the previous."""
    spec = build_window_spec(period, end or date.today())
    cur_lo = datetime.combine(spec.current_start, time.min)
    cur_hi = datetime.combine(spec.current_end, time.min)
    prev_lo = datetime.combine(spec.previous_start, time.min)

    current_counts: dict[str, int] = {}
    previous_counts: dict[str, int] = {}
    current_importance: dict[str, float] = {}
    total_current = 0
    total_previous = 0

    for title, importance, published_at, created_at in _fetch(session, prev_lo, cur_hi):
        anchor = _anchor(published_at, created_at)
        if anchor is None:
            continue
        if cur_lo <= anchor < cur_hi:
            total_current += 1
            for term in title_terms(title):
                current_counts[term] = current_counts.get(term, 0) + 1
                current_importance[term] = current_importance.get(term, 0.0) + (
                    importance or 0.0
                )
        elif prev_lo <= anchor < cur_lo:
            total_previous += 1
            for term in title_terms(title):
                previous_counts[term] = previous_counts.get(term, 0) + 1

    buckets = compare_windows(
        current_counts,
        previous_counts,
        importance=current_importance,
        top_n=top_n,
        min_count=min_count,
    )
    return TrendReport(
        window=spec,
        rising=buckets.rising,
        fading=buckets.fading,
        new=buckets.new,
        dropped=buckets.dropped,
        top_current=buckets.top_current,
        total_current_items=total_current,
        total_previous_items=total_previous,
    )


def _fetch(session: Session, lo: datetime, hi: datetime):
    """Rows whose anchor (published_at, else created_at) falls in [lo, hi)."""
    stmt = (
        select(
            ProcessedItem.normalized_title,
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


__all__ = ["analyze_trends", "build_window_spec"]
