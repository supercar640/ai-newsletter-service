"""integrate(): company-interest rows boost matching items' importance."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.core.embeddings import serialize
from newsletter.models.company_interest import CompanyInterest
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.integration.service import integrate
from newsletter.slices.interests import repository as interests_repo
from newsletter.slices.interests.schemas import InterestCreate
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


def _seed_item(db_session: Session, *, title: str, embedding: list[float] | None = None) -> int:
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
        embedding=serialize(embedding) if embedding else None,
        embedding_model="stub" if embedding else None,
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


def test_interest_boost_lifts_matching_item_above_non_matching(db_session: Session) -> None:
    _seed_source(db_session)
    matched = _seed_item(db_session, title="RAG framework launches")
    other = _seed_item(db_session, title="Bitcoin price update")
    db_session.commit()

    # Without interests — baseline score (same recency/trust for both → equal).
    integrate(db_session, now=_NOW)
    db_session.commit()
    base_matched = _final_score(db_session, matched)
    base_other = _final_score(db_session, other)
    assert base_matched == base_other

    # Register an interest matching "rag" — only `matched` should rise.
    interests_repo.add(
        db_session,
        InterestCreate(name="RAG", keywords=["rag"], weight=2.0),
    )
    db_session.commit()

    integrate(db_session, now=_NOW)
    db_session.commit()
    assert _final_score(db_session, matched) > base_matched
    assert _final_score(db_session, other) == base_other


def test_disabled_interest_is_ignored(db_session: Session) -> None:
    _seed_source(db_session)
    item = _seed_item(db_session, title="RAG news")
    row = interests_repo.add(
        db_session, InterestCreate(name="RAG", keywords=["rag"], weight=2.0)
    )
    db_session.commit()

    integrate(db_session, now=_NOW)
    db_session.commit()
    boosted = _final_score(db_session, item)

    interests_repo.disable(db_session, row.id)
    db_session.commit()
    integrate(db_session, now=_NOW)
    db_session.commit()
    assert _final_score(db_session, item) < boosted


def test_embedding_only_match_boosts_when_keyword_misses(db_session: Session) -> None:
    _seed_source(db_session)
    # Item has an embedding; no keyword in its title.
    item = _seed_item(
        db_session,
        title="알파벳, 의미 기반 검색 도입",
        embedding=[1.0, 0.0, 0.0],
    )
    db_session.commit()

    # Interest with NO keyword overlap, but a similar embedding vector.
    row = CompanyInterest(
        name="semantic search",
        keywords_json="[]",
        weight=2.0,
        enabled=True,
        embedding=serialize([0.96, 0.28, 0.0]),  # cos ≈ 0.96
        embedding_model="stub",
    )
    db_session.add(row)
    db_session.commit()

    integrate(db_session, now=_NOW)
    db_session.commit()
    boosted = _final_score(db_session, item)

    # Disable to compare against baseline.
    interests_repo.disable(db_session, row.id)
    db_session.commit()
    integrate(db_session, now=_NOW)
    db_session.commit()
    baseline = _final_score(db_session, item)

    assert boosted > baseline
