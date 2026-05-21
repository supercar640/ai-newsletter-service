"""integrate(): corpus chunks boost matching items' importance."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.corpus import repository as corpus_repo
from newsletter.slices.corpus.repository import ChunkInsert
from newsletter.slices.integration.service import integrate
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate

_NOW = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)


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


def _seed_item(db_session: Session, *, title: str) -> int:
    raw = RawItem(
        source_id="src",
        title=title,
        url=f"https://example.com/{title[:24]}",
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
    )
    db_session.add(proc)
    db_session.flush()
    return proc.id


def _final_score(db_session: Session, proc_id: int) -> float:
    return float(
        db_session.scalars(
            select(ProcessedItem.importance_score).where(ProcessedItem.id == proc_id)
        ).one()
    )


def test_corpus_chunk_boosts_matching_item(db_session: Session) -> None:
    _seed_source(db_session)
    matched = _seed_item(db_session, title="RAG agent vector pipeline")
    other = _seed_item(db_session, title="Bitcoin price update today")
    db_session.commit()

    integrate(db_session, now=_NOW)
    db_session.commit()
    base_matched = _final_score(db_session, matched)
    base_other = _final_score(db_session, other)

    corpus_repo.replace_file_chunks(
        db_session,
        source_path="company/focus.md",
        file_hash="h1",
        chunks=[
            ChunkInsert(
                text="우리는 rag agent vector 에 집중한다",
                keywords=["rag", "agent", "vector"],
                embedding=None,
                embedding_model=None,
            )
        ],
    )
    db_session.commit()

    integrate(db_session, now=_NOW)
    db_session.commit()
    assert _final_score(db_session, matched) > base_matched
    assert _final_score(db_session, other) == base_other


def test_no_chunks_leaves_scores_unchanged(db_session: Session) -> None:
    _seed_source(db_session)
    item = _seed_item(db_session, title="RAG agent vector")
    db_session.commit()
    integrate(db_session, now=_NOW)
    db_session.commit()
    before = _final_score(db_session, item)

    integrate(db_session, now=_NOW)
    db_session.commit()
    assert _final_score(db_session, item) == before
