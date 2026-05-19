"""Company-interest multiplier in scoring (Phase 2)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from newsletter.slices.integration.scoring import (
    InterestProfile,
    ScoreInput,
    interest_match_factor,
    score_items,
)


def _profile(
    *,
    name: str = "RAG",
    keywords: tuple[str, ...] = (),
    weight: float = 1.0,
    embedding: list[float] | None = None,
) -> InterestProfile:
    return InterestProfile(
        id=1,
        name=name,
        keywords=tuple(k.lower() for k in keywords),
        weight=weight,
        embedding=embedding,
    )


# ---------------------------------------------------------------------------
# interest_match_factor — pure function
# ---------------------------------------------------------------------------


def test_no_interests_returns_one():
    assert (
        interest_match_factor(
            title="anything",
            summary="goes here",
            item_embedding=None,
            interests=[],
        )
        == 1.0
    )


def test_keyword_match_in_title_boosts():
    f = interest_match_factor(
        title="New RAG framework released",
        summary=None,
        item_embedding=None,
        interests=[_profile(keywords=("rag",), weight=1.0)],
    )
    assert f > 1.0
    assert f <= 1.5


def test_keyword_match_in_summary_boosts():
    f = interest_match_factor(
        title="Tooling update",
        summary="Adds support for retrieval augmented generation pipelines.",
        item_embedding=None,
        interests=[_profile(keywords=("retrieval augmented",), weight=1.0)],
    )
    assert f > 1.0


def test_no_keyword_no_embedding_returns_one():
    f = interest_match_factor(
        title="Bitcoin price update",
        summary="Crypto market moves.",
        item_embedding=None,
        interests=[_profile(keywords=("rag", "llm"), weight=2.0)],
    )
    assert f == 1.0


def test_embedding_cosine_above_threshold_boosts_without_keyword():
    """Semantic match should fire even when no keyword hits."""
    f = interest_match_factor(
        title="Alphabet 검색에 의미 기반 검색 도입",
        summary=None,
        item_embedding=[1.0, 0.0, 0.0],
        interests=[
            _profile(
                keywords=(),  # no keyword hit
                weight=1.0,
                embedding=[0.95, 0.31, 0.0],  # cos ≈ 0.95 → above threshold
            )
        ],
    )
    assert f > 1.0


def test_embedding_cosine_below_threshold_no_boost():
    f = interest_match_factor(
        title="random title",
        summary=None,
        item_embedding=[1.0, 0.0, 0.0],
        interests=[
            _profile(
                keywords=(),
                weight=1.0,
                embedding=[0.0, 1.0, 0.0],  # cos = 0
            )
        ],
    )
    assert f == 1.0


def test_higher_weight_means_higher_boost():
    low = interest_match_factor(
        title="RAG framework",
        summary=None,
        item_embedding=None,
        interests=[_profile(keywords=("rag",), weight=1.0)],
    )
    high = interest_match_factor(
        title="RAG framework",
        summary=None,
        item_embedding=None,
        interests=[_profile(keywords=("rag",), weight=3.0)],
    )
    assert high > low


def test_multiplier_is_capped_at_one_point_five():
    # Many strong matches x big weight — must clamp.
    interests = [
        _profile(keywords=("rag",), weight=5.0),
        _profile(name="b", keywords=("rag",), weight=5.0),
        _profile(name="c", keywords=("rag",), weight=5.0),
        _profile(name="d", keywords=("rag",), weight=5.0),
    ]
    f = interest_match_factor(
        title="RAG RAG RAG", summary=None, item_embedding=None, interests=interests
    )
    assert f == pytest.approx(1.5)


def test_case_insensitive_keyword_match():
    f = interest_match_factor(
        title="RAG framework",
        summary=None,
        item_embedding=None,
        interests=[_profile(keywords=("rag",), weight=1.0)],
    )
    assert f > 1.0


# ---------------------------------------------------------------------------
# score_items integration
# ---------------------------------------------------------------------------


_NOW = datetime(2026, 5, 19, tzinfo=UTC)


def _score_input(item_id: int, title: str) -> ScoreInput:
    return ScoreInput(
        id=item_id,
        trust_level="media",
        published_at=_NOW,
        title=title,
        summary=None,
        source_name="src",
    )


def test_score_items_applies_interest_multiplier_without_llm():
    items = [
        _score_input(1, "RAG framework released"),
        _score_input(2, "Bitcoin price update"),
    ]
    base = score_items(items, llm=None, now=_NOW)
    boosted = score_items(
        items,
        llm=None,
        now=_NOW,
        interests=[_profile(keywords=("rag",), weight=1.0)],
    )
    # Item 1 (matches "rag") gets boosted; item 2 does not.
    assert boosted[1] > base[1]
    assert boosted[2] == pytest.approx(base[2])


def test_score_items_uses_item_embedding_when_provided():
    items = [_score_input(1, "Alphabet semantic search news")]
    embeddings = {1: [1.0, 0.0, 0.0]}
    base = score_items(items, llm=None, now=_NOW)
    boosted = score_items(
        items,
        llm=None,
        now=_NOW,
        interests=[
            _profile(
                keywords=(),  # forces embedding path
                weight=1.0,
                embedding=[0.95, 0.31, 0.0],
            )
        ],
        item_embeddings=embeddings,
    )
    assert boosted[1] > base[1]


def test_score_items_no_interests_matches_legacy_behavior():
    items = [_score_input(1, "Anything")]
    base = score_items(items, llm=None, now=_NOW)
    same = score_items(items, llm=None, now=_NOW, interests=None)
    assert base == same
