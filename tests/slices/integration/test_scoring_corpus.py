"""scoring.corpus_relevance_factor — company-document relevance boost."""

from __future__ import annotations

from datetime import UTC, datetime

from newsletter.slices.integration.scoring import (
    CorpusChunk,
    ScoreInput,
    corpus_relevance_factor,
    score_items,
)

_NOW = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)


def test_no_chunks_returns_neutral():
    factor = corpus_relevance_factor(
        title="anything", summary=None, item_embedding=None, chunks=[]
    )
    assert factor == 1.0


def test_keyword_fallback_boosts_on_overlap():
    chunks = [CorpusChunk(keywords=("rag", "agent", "vector"), embedding=None)]
    factor = corpus_relevance_factor(
        title="New RAG agent vector pipeline",
        summary=None,
        item_embedding=None,
        chunks=chunks,
    )
    # 3 distinct hits == saturation -> full strength -> 1.0 + 1.0 * 0.3
    assert factor == 1.3


def test_keyword_fallback_partial_overlap():
    chunks = [CorpusChunk(keywords=("rag", "agent", "vector"), embedding=None)]
    factor = corpus_relevance_factor(
        title="A RAG note", summary=None, item_embedding=None, chunks=chunks
    )
    # 1 hit / saturation(3) -> strength 1/3
    assert abs(factor - (1.0 + (1 / 3) * 0.3)) < 1e-9


def test_embedding_path_scales_with_cosine():
    chunks = [CorpusChunk(keywords=(), embedding=[1.0, 0.0, 0.0])]
    factor = corpus_relevance_factor(
        title="x", summary=None, item_embedding=[1.0, 0.0, 0.0], chunks=chunks
    )
    # cosine 1.0 -> strength 1.0 -> cap clamp 1.3
    assert factor == 1.3


def test_embedding_below_threshold_is_neutral():
    chunks = [CorpusChunk(keywords=(), embedding=[0.0, 1.0, 0.0])]
    factor = corpus_relevance_factor(
        title="x", summary=None, item_embedding=[1.0, 0.0, 0.0], chunks=chunks
    )
    assert factor == 1.0


def test_score_items_applies_corpus_boost():
    item = ScoreInput(
        id=1,
        trust_level="media",
        published_at=_NOW,
        title="RAG agent vector",
        summary=None,
        source_name="src",
    )
    chunks = [CorpusChunk(keywords=("rag", "agent", "vector"), embedding=None)]
    base = score_items([item], llm=None, now=_NOW)
    boosted = score_items([item], llm=None, now=_NOW, corpus_chunks=chunks)
    assert boosted[1] > base[1]
