"""dashboard.service — window aggregation over collected/processed items."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.dashboard.service import build_dashboard
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate

_UNTIL = date(2026, 5, 22)


def _seed_source(db_session: Session, source_id: str = "src", name: str = "Src") -> None:
    sources_repo.add(
        db_session,
        SourceCreate(
            source_id=source_id,
            name=name,
            type="RSS",
            content_track="expert_news",  # type: ignore[arg-type]
            endpoint="https://example.com",
            category="AI Model",
            trust_level="media",  # type: ignore[arg-type]
        ),
    )


def _seed_raw(
    db_session: Session,
    *,
    source_id: str = "src",
    title: str,
    collected_at: datetime,
) -> RawItem:
    raw = RawItem(
        source_id=source_id,
        title=title,
        url=f"https://example.com/{source_id}/{title}",
        published_at=collected_at,
        collected_at=collected_at,
        raw_summary=title,
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    return raw


def _process(
    db_session: Session,
    raw: RawItem,
    *,
    relevance: float,
    importance: float,
    track: str = "expert_news",
    category: str | None = "AI Model",
    group: str | None = None,
) -> None:
    db_session.add(
        ProcessedItem(
            raw_item_id=raw.id,
            normalized_title=raw.title,
            canonical_url=raw.url,
            content_track=track,
            category=category,
            relevance_score=relevance,
            importance_score=importance,
            summary=raw.title,
            keywords=None,
            duplicate_group_id=group,
        )
    )
    db_session.flush()


def test_per_source_yield_and_avg_scores(db_session: Session):
    _seed_source(db_session)
    r1 = _seed_raw(db_session, title="a", collected_at=datetime(2026, 5, 20, 9, 0))
    r2 = _seed_raw(db_session, title="b", collected_at=datetime(2026, 5, 20, 10, 0))
    _process(db_session, r1, relevance=0.8, importance=2.0)
    _process(db_session, r2, relevance=0.4, importance=4.0)
    db_session.commit()

    report = build_dashboard(db_session, days=7, until=_UNTIL)
    assert len(report.sources) == 1
    s = report.sources[0]
    assert s.collected == 2
    assert s.processed == 2
    assert s.avg_relevance == 0.6
    assert s.avg_importance == 3.0


def test_unprocessed_rawitem_counted_as_collected_only(db_session: Session):
    _seed_source(db_session)
    _seed_raw(db_session, title="unprocessed", collected_at=datetime(2026, 5, 20, 9, 0))
    db_session.commit()
    report = build_dashboard(db_session, days=7, until=_UNTIL)
    s = report.sources[0]
    assert s.collected == 1
    assert s.processed == 0
    assert s.avg_relevance == 0.0
    assert s.avg_importance == 0.0
    assert report.quality.total_collected == 1
    assert report.quality.total_processed == 0


def test_window_filtering(db_session: Session):
    _seed_source(db_session)
    _seed_raw(db_session, title="in", collected_at=datetime(2026, 5, 20, 9, 0))
    _seed_raw(db_session, title="old", collected_at=datetime(2026, 4, 1, 9, 0))
    db_session.commit()
    report = build_dashboard(db_session, days=7, until=_UNTIL)
    assert report.quality.total_collected == 1


def test_quality_summary(db_session: Session):
    _seed_source(db_session)
    r1 = _seed_raw(db_session, title="a", collected_at=datetime(2026, 5, 20, 9, 0))
    r2 = _seed_raw(db_session, title="b", collected_at=datetime(2026, 5, 20, 10, 0))
    r3 = _seed_raw(db_session, title="c", collected_at=datetime(2026, 5, 20, 11, 0))
    _process(
        db_session,
        r1,
        relevance=0.9,
        importance=1.0,
        track="expert_news",
        category="LLM",
        group="g1",
    )
    _process(
        db_session,
        r2,
        relevance=0.9,
        importance=1.0,
        track="expert_news",
        category="LLM",
        group="g1",
    )
    _process(
        db_session,
        r3,
        relevance=0.9,
        importance=1.0,
        track="practical_insight",
        category="Tooling",
        group=None,
    )
    db_session.commit()

    q = build_dashboard(db_session, days=7, until=_UNTIL).quality
    assert q.total_processed == 3
    assert q.track_counts == {"expert_news": 2, "practical_insight": 1}
    assert q.top_categories[0] == ("LLM", 2)
    assert q.distinct_groups == 1
    assert q.grouped_items == 2


def test_empty_window(db_session: Session):
    report = build_dashboard(db_session, days=7, until=_UNTIL)
    assert report.sources == []
    assert report.quality.total_collected == 0
    assert report.quality.top_categories == []
