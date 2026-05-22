"""monthly.service — calendar-month aggregation."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.monthly.service import build_monthly_report
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate


def _seed_source(db_session: Session) -> None:
    sources_repo.add(
        db_session,
        SourceCreate(
            source_id="src",
            name="src",
            type="RSS",
            content_track="expert_news",  # type: ignore[arg-type]
            endpoint="https://example.com",
            category="AI Model",
            trust_level="media",  # type: ignore[arg-type]
        ),
    )


def _seed_item(
    db_session: Session,
    *,
    title: str,
    importance: float,
    published_at: datetime,
    summary: str = "summary",
) -> None:
    raw = RawItem(
        source_id="src",
        title=title,
        url=f"https://example.com/{title[:20]}-{published_at}",
        published_at=published_at,
        raw_summary=summary,
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(
        ProcessedItem(
            raw_item_id=raw.id,
            normalized_title=title,
            canonical_url=raw.url,
            content_track="expert_news",
            category="AI Model",
            relevance_score=0.9,
            importance_score=importance,
            summary=summary,
            keywords=None,
            duplicate_group_id=None,
        )
    )
    db_session.flush()


def test_aggregates_calendar_month(db_session: Session):
    _seed_source(db_session)
    _seed_item(
        db_session, title="In April A", importance=2.0, published_at=datetime(2026, 4, 10, 9, 0)
    )
    _seed_item(
        db_session, title="In April B", importance=5.0, published_at=datetime(2026, 4, 20, 9, 0)
    )
    _seed_item(db_session, title="In May", importance=9.0, published_at=datetime(2026, 5, 2, 9, 0))
    db_session.commit()

    report = build_monthly_report(db_session, month=date(2026, 4, 15))
    assert report.month == "2026-04"
    assert report.since == date(2026, 4, 1)
    assert report.until == date(2026, 5, 1)
    assert report.total_items == 2
    assert report.top_headlines[0].title == "In April B"
    assert report.top_headlines[0].importance == 5.0
    assert report.trend.total_current_items >= 0
    assert report.competitors.competitors == []


def test_top_headlines_truncated_to_top_k(db_session: Session):
    _seed_source(db_session)
    for i in range(5):
        _seed_item(
            db_session,
            title=f"Item {i}",
            importance=float(i),
            published_at=datetime(2026, 4, 10, 9, 0),
        )
    db_session.commit()
    report = build_monthly_report(db_session, month=date(2026, 4, 1), top_k=3)
    assert report.total_items == 5
    assert len(report.top_headlines) == 3
    assert [h.importance for h in report.top_headlines] == [4.0, 3.0, 2.0]


def test_default_month_is_previous_completed_month(db_session: Session):
    from newsletter.slices.monthly.service import _month_bounds, _previous_month_first

    assert _previous_month_first(date(2026, 5, 22)) == date(2026, 4, 1)
    assert _previous_month_first(date(2026, 1, 3)) == date(2025, 12, 1)
    assert _month_bounds(date(2026, 12, 9)) == (date(2026, 12, 1), date(2027, 1, 1))


def test_empty_month_returns_zero_items(db_session: Session):
    report = build_monthly_report(db_session, month=date(2026, 4, 1))
    assert report.total_items == 0
    assert report.top_headlines == []
