"""Monthly digest aggregation over accumulated ProcessedItem rows.

Reuses the trends and competitors services for their sections, plus an
importance-ranked "top headlines" query whose ordering already reflects the
company-interest scoring boost. DB-only; the LLM narrative is added separately.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.competitors.service import analyze_competitors
from newsletter.slices.monthly.schemas import MonthlyReport, TopHeadline
from newsletter.slices.trends.service import analyze_trends


def _month_bounds(month: date) -> tuple[date, date]:
    """First day of ``month`` and first day of the next month (exclusive)."""
    since = month.replace(day=1)
    if since.month == 12:
        until = since.replace(year=since.year + 1, month=1)
    else:
        until = since.replace(month=since.month + 1)
    return since, until


def _previous_month_first(today: date) -> date:
    """First day of the month before ``today``'s month."""
    first_this = today.replace(day=1)
    return (first_this - timedelta(days=1)).replace(day=1)


def build_monthly_report(
    session: Session, *, month: date | None = None, top_k: int = 10
) -> MonthlyReport:
    """Aggregate trends + competitors + top headlines for one calendar month."""
    target = month or _previous_month_first(date.today())
    since, until = _month_bounds(target)

    trend = analyze_trends(session, period="month", end=until - timedelta(days=1))
    competitors = analyze_competitors(session, since=since, until=until, top_k=5)

    lo = datetime.combine(since, time.min)
    hi = datetime.combine(until, time.min)
    total_items = 0
    headlines: list[TopHeadline] = []
    for title, url, importance, category, summary, published_at, created_at in _fetch(
        session, lo, hi
    ):
        anchor = _anchor(published_at, created_at)
        if anchor is None or not (lo <= anchor < hi):
            continue
        total_items += 1
        headlines.append(
            TopHeadline(
                title=title,
                url=url,
                importance=importance or 0.0,
                category=category,
                summary=summary,
            )
        )
    headlines.sort(key=lambda h: h.importance, reverse=True)

    return MonthlyReport(
        month=target.strftime("%Y-%m"),
        since=since,
        until=until,
        total_items=total_items,
        trend=trend,
        competitors=competitors,
        top_headlines=headlines[:top_k],
    )


def _fetch(session: Session, lo: datetime, hi: datetime):
    """Rows whose anchor (published_at, else created_at) falls in [lo, hi)."""
    stmt = (
        select(
            ProcessedItem.normalized_title,
            ProcessedItem.canonical_url,
            ProcessedItem.importance_score,
            ProcessedItem.category,
            ProcessedItem.summary,
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
    dt = published_at if published_at is not None else created_at
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


__all__ = ["build_monthly_report"]
