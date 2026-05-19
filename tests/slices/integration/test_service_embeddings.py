"""integrate(): embeddings flow from ProcessedItem to clustering."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from newsletter.core.embeddings import serialize
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.integration.service import integrate
from newsletter.slices.sources import repository
from newsletter.slices.sources.schemas import SourceCreate

_NOW = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)


def _seed_source(db_session: Session, source_id: str) -> None:
    repository.add(
        db_session,
        SourceCreate(
            source_id=source_id,
            name=source_id,
            type="RSS",
            content_track="expert_news",  # type: ignore[arg-type]
            endpoint="https://example.com",
            category="AI Model",
            trust_level="media",  # type: ignore[arg-type]
        ),
    )


def _seed_proc(
    db_session: Session,
    *,
    source_id: str,
    title: str,
    embedding: list[float] | None,
) -> ProcessedItem:
    raw = RawItem(
        source_id=source_id,
        title=title,
        url=f"https://example.com/{title[:20]}",
        published_at=_NOW,
        raw_summary=title,
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    proc = ProcessedItem(
        raw_item_id=raw.id,
        normalized_title=title,
        canonical_url=raw.url,
        content_track="expert_news",
        category="AI Model",
        relevance_score=0.9,
        importance_score=0.0,
        summary=title,
        keywords=None,
        duplicate_group_id=None,
        embedding=serialize(embedding) if embedding else None,
        embedding_model="stub" if embedding else None,
    )
    db_session.add(proc)
    db_session.flush()
    return proc


def test_integrate_clusters_two_items_only_when_embeddings_say_so(
    db_session: Session,
) -> None:
    _seed_source(db_session, "src")

    # Lexically disjoint titles → Jaccard wouldn't merge. Embeddings will.
    _seed_proc(
        db_session,
        source_id="src",
        title="알파벳, AI 검색 통합 발표",
        embedding=[1.0, 0.0, 0.0],
    )
    _seed_proc(
        db_session,
        source_id="src",
        title="Google rolls semantic search into Gemini",
        embedding=[0.97, 0.24, 0.0],
    )
    db_session.commit()

    report = integrate(db_session, now=_NOW, expert_count=5, practical_count=5)
    db_session.commit()

    # Two items merged into one cluster via embedding similarity.
    assert report.scored == 2
    assert report.clusters == 1


def test_integrate_keeps_items_separate_without_embeddings(db_session: Session) -> None:
    """Same lexically-disjoint pair, but no embeddings → two clusters."""
    _seed_source(db_session, "src")
    _seed_proc(
        db_session,
        source_id="src",
        title="알파벳, AI 검색 통합 발표",
        embedding=None,
    )
    _seed_proc(
        db_session,
        source_id="src",
        title="Google rolls semantic search into Gemini",
        embedding=None,
    )
    db_session.commit()

    report = integrate(db_session, now=_NOW, expert_count=5, practical_count=5)
    db_session.commit()

    assert report.scored == 2
    assert report.clusters == 2
