"""End-to-end service tests using in-memory DB + stubbed LLM."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.processing.service import process
from newsletter.slices.sources import repository
from newsletter.slices.sources.schemas import SourceCreate


def _seed_source(
    db_session: Session, *, source_id: str = "src", track: str = "expert_news"
) -> None:
    repository.add(
        db_session,
        SourceCreate(
            source_id=source_id,
            name=source_id,
            type="RSS",
            content_track=track,  # type: ignore[arg-type]
            endpoint="https://example.com",
            category="AI Model",
        ),
    )


def _seed_raw(db_session: Session, **kwargs) -> RawItem:
    raw = RawItem(
        source_id=kwargs.get("source_id", "src"),
        title=kwargs.get("title", "OpenAI launches GPT-5"),
        url=kwargs.get("url", "https://example.com/x"),
        published_at=kwargs.get("published_at", datetime(2025, 5, 12, tzinfo=UTC)),
        raw_summary=kwargs.get("raw_summary", "A new model from OpenAI."),
        raw_content=kwargs.get("raw_content"),
        language=kwargs.get("language", "en"),
    )
    db_session.add(raw)
    db_session.flush()
    return raw


def test_process_creates_one_row_per_raw(db_session: Session) -> None:
    _seed_source(db_session)
    _seed_raw(db_session, url="https://example.com/a", title="AI model GPT release")
    _seed_raw(
        db_session,
        url="https://example.com/b",
        title="Anthropic announces new Claude version",
    )
    db_session.commit()

    report = process(db_session, keyword_only=True)
    db_session.commit()

    assert report.fetched == 2
    assert report.processed == 2
    assert db_session.scalars(select(ProcessedItem)).all()


def test_process_is_idempotent(db_session: Session) -> None:
    _seed_source(db_session)
    _seed_raw(db_session, title="OpenAI GPT release", url="https://example.com/a")
    db_session.commit()

    process(db_session, keyword_only=True)
    db_session.commit()
    report = process(db_session, keyword_only=True)
    db_session.commit()
    assert report.fetched == 0
    assert report.processed == 0


def test_process_filters_out_non_ai_with_min_relevance(db_session: Session) -> None:
    _seed_source(db_session)
    _seed_raw(
        db_session,
        title="Tesla earnings beat forecast",
        raw_summary="Quarterly results",
        url="https://example.com/tesla",
    )
    db_session.commit()

    report = process(db_session, keyword_only=True, min_relevance=0.1)
    db_session.commit()
    assert report.fetched == 1
    assert report.processed == 0
    assert report.filtered_out == 1


def test_process_dedupes_by_canonical_url(db_session: Session) -> None:
    _seed_source(db_session)
    _seed_raw(db_session, title="AI launch", url="https://example.com/x?utm_source=feed")
    _seed_raw(db_session, title="AI launch", url="https://example.com/x")
    db_session.commit()

    process(db_session, keyword_only=True)
    db_session.commit()

    rows = db_session.scalars(select(ProcessedItem)).all()
    # Both items processed, but they share a duplicate_group_id.
    assert len(rows) == 2
    group_ids = {r.duplicate_group_id for r in rows}
    assert len(group_ids) == 1


def test_process_sets_track_from_source(db_session: Session) -> None:
    _seed_source(db_session, track="practical_insight")
    _seed_raw(db_session, title="AI productivity tips", url="https://example.com/a")
    db_session.commit()

    process(db_session, keyword_only=True)
    db_session.commit()
    rows = db_session.scalars(select(ProcessedItem)).all()
    assert rows[0].content_track == "practical_insight"


def test_process_writes_keywords_string(db_session: Session) -> None:
    _seed_source(db_session)
    _seed_raw(db_session, title="OpenAI launches GPT-5 LLM", url="https://example.com/a")
    db_session.commit()

    process(db_session, keyword_only=True)
    db_session.commit()
    row = db_session.scalars(select(ProcessedItem)).first()
    assert row is not None
    assert row.keywords is not None
    assert "GPT" in row.keywords or "OpenAI" in row.keywords or "LLM" in row.keywords


# Note: a missing-source scenario can't occur with our FK setup
# (raw_items.source_id has ON DELETE CASCADE pointing at sources), so
# there is no test for that branch.
