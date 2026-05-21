"""trends.service — window math + DB aggregation."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate
from newsletter.slices.trends.service import analyze_trends, build_window_spec

_END = date(2026, 5, 21)


def test_build_window_spec_week():
    spec = build_window_spec("week", _END)
    # current covers the 7 days ending on _END inclusive -> [05-15, 05-22)
    assert spec.current_start == date(2026, 5, 15)
    assert spec.current_end == date(2026, 5, 22)
    assert spec.previous_start == date(2026, 5, 8)
    assert spec.previous_end == date(2026, 5, 15)


def test_build_window_spec_rejects_bad_period():
    import pytest

    with pytest.raises(ValueError):
        build_window_spec("yearly", _END)


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


def _seed(
    db_session: Session,
    *,
    title: str,
    published_at: datetime | None,
    created_at: datetime | None = None,
) -> None:
    raw = RawItem(
        source_id="src",
        title=title,
        url=f"https://example.com/{title[:24]}-{published_at}",
        published_at=published_at,
        raw_summary=title,
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    kwargs = {}
    if created_at is not None:
        kwargs["created_at"] = created_at
    proc = ProcessedItem(
        raw_item_id=raw.id,
        normalized_title=title,
        canonical_url=raw.url,
        content_track="expert_news",
        category="AI Model",
        relevance_score=0.9,
        importance_score=1.0,
        summary=title,
        keywords=None,
        duplicate_group_id=None,
        **kwargs,
    )
    db_session.add(proc)
    db_session.flush()


def test_analyze_splits_current_and_previous(db_session: Session):
    _seed_source(db_session)
    # current window item (in [05-15, 05-22))
    _seed(db_session, title="Sora video model", published_at=datetime(2026, 5, 18, 9, 0))
    # previous window item (in [05-08, 05-15))
    _seed(db_session, title="Clubhouse audio app", published_at=datetime(2026, 5, 10, 9, 0))
    db_session.commit()

    report = analyze_trends(db_session, period="week", end=_END, min_count=1)
    assert report.total_current_items == 1
    assert report.total_previous_items == 1
    new_terms = {d.term for d in report.new}
    dropped_terms = {d.term for d in report.dropped}
    assert "sora" in new_terms
    assert "clubhouse" in dropped_terms


def test_analyze_falls_back_to_created_at_when_published_is_null(db_session: Session):
    _seed_source(db_session)
    _seed(
        db_session,
        title="Fallback topic here",
        published_at=None,
        created_at=datetime(2026, 5, 18, 9, 0),  # current window
    )
    db_session.commit()
    report = analyze_trends(db_session, period="week", end=_END, min_count=1)
    assert report.total_current_items == 1
    assert "fallback" in {d.term for d in report.new}


def test_analyze_empty_window(db_session: Session):
    report = analyze_trends(db_session, period="week", end=_END)
    assert report.total_current_items == 0
    assert report.total_previous_items == 0
    assert report.new == []
