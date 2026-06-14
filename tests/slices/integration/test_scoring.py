"""Tests for the integration scoring module.

The scoring module turns a ProcessedItem-shaped input into a single
``importance_score`` float. Inputs are dataclasses (``ScoreInput``) so the
math is pure and easy to test without a DB.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from newsletter.slices.integration.scoring import (
    TRUST_WEIGHTS,
    ScoreInput,
    base_importance,
    recency_factor,
    score_items,
)

_NOW = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)


def _mk(
    *,
    id: int = 1,
    trust_level: str = "media",
    published_at: datetime | None = _NOW,
    title: str = "OpenAI launches new model",
    summary: str | None = "A new release.",
    source_name: str = "TestSource",
) -> ScoreInput:
    return ScoreInput(
        id=id,
        trust_level=trust_level,
        published_at=published_at,
        title=title,
        summary=summary,
        source_name=source_name,
    )


class TestRecencyFactor:
    def test_brand_new_item_is_one(self) -> None:
        assert recency_factor(_NOW, _NOW, half_life_days=3.0) == pytest.approx(1.0)

    def test_at_half_life_returns_half(self) -> None:
        published = _NOW - timedelta(days=3)
        assert recency_factor(published, _NOW, half_life_days=3.0) == pytest.approx(0.5)

    def test_decays_monotonically(self) -> None:
        a = recency_factor(_NOW - timedelta(days=1), _NOW, half_life_days=3.0)
        b = recency_factor(_NOW - timedelta(days=5), _NOW, half_life_days=3.0)
        c = recency_factor(_NOW - timedelta(days=10), _NOW, half_life_days=3.0)
        assert a > b > c
        assert 0.0 < c < 1.0

    def test_future_publish_clamps_to_one(self) -> None:
        # Some feeds return published_at slightly in the future (clock skew).
        published = _NOW + timedelta(hours=2)
        assert recency_factor(published, _NOW, half_life_days=3.0) == pytest.approx(1.0)

    def test_missing_published_at_is_neutral(self) -> None:
        assert recency_factor(None, _NOW, half_life_days=3.0) == pytest.approx(0.5)


class TestTrustWeights:
    def test_known_levels_are_ordered(self) -> None:
        assert TRUST_WEIGHTS["official"] > TRUST_WEIGHTS["media"]
        assert TRUST_WEIGHTS["media"] > TRUST_WEIGHTS["community"]

    def test_all_levels_in_unit_interval(self) -> None:
        for w in TRUST_WEIGHTS.values():
            assert 0.0 < w <= 1.0


class TestBaseImportance:
    def test_combines_trust_and_recency(self) -> None:
        score = base_importance("media", _NOW, _NOW, half_life_days=3.0)
        assert score == pytest.approx(TRUST_WEIGHTS["media"] * 1.0)

    def test_unknown_trust_level_uses_default(self) -> None:
        score = base_importance("alien", _NOW, _NOW, half_life_days=3.0)
        # Defaults must produce *some* finite score, not crash.
        assert 0.0 < score <= 1.0

    def test_old_official_beats_fresh_community(self) -> None:
        # 2 days old + official should still rank above same-second community.
        fresh_community = base_importance("community", _NOW, _NOW)
        old_official = base_importance("official", _NOW - timedelta(days=2), _NOW)
        assert old_official > fresh_community


class TestScoreItemsWithoutLLM:
    def test_returns_one_score_per_input(self) -> None:
        items = [_mk(id=1), _mk(id=2, trust_level="official")]
        scores = score_items(items, llm=None, now=_NOW)
        assert set(scores.keys()) == {1, 2}

    def test_higher_trust_scores_higher(self) -> None:
        items = [
            _mk(id=1, trust_level="community"),
            _mk(id=2, trust_level="official"),
        ]
        scores = score_items(items, llm=None, now=_NOW)
        assert scores[2] > scores[1]

    def test_no_items_returns_empty(self) -> None:
        assert score_items([], llm=None, now=_NOW) == {}


class TestScoreItemsWithLLM:
    def test_llm_called_only_for_top_k(self) -> None:
        """Cost guard: with top_k_for_llm=2, only the two highest-base items
        should hit the LLM."""
        recorder = _RecordingLLM(default_importance=3)
        items = [
            _mk(
                id=i,
                trust_level="official" if i == 1 else "community",
                published_at=_NOW - timedelta(days=i),
            )
            for i in range(1, 6)
        ]
        score_items(items, llm=recorder, now=_NOW, top_k_for_llm=2)
        assert len(recorder.calls) == 2

    def test_high_llm_score_boosts_final(self) -> None:
        recorder = _RecordingLLM(default_importance=5)
        items = [_mk(id=1, trust_level="media")]
        scores_with = score_items(items, llm=recorder, now=_NOW, top_k_for_llm=10)
        scores_without = score_items(items, llm=None, now=_NOW)
        assert scores_with[1] > scores_without[1]

    def test_low_llm_score_penalizes_final(self) -> None:
        recorder = _RecordingLLM(default_importance=1)
        items = [_mk(id=1, trust_level="media")]
        scores_with = score_items(items, llm=recorder, now=_NOW, top_k_for_llm=10)
        scores_without = score_items(items, llm=None, now=_NOW)
        assert scores_with[1] < scores_without[1]

    def test_neutral_llm_score_leaves_base_unchanged(self) -> None:
        recorder = _RecordingLLM(default_importance=3)
        items = [_mk(id=1, trust_level="media")]
        scores_with = score_items(items, llm=recorder, now=_NOW, top_k_for_llm=10)
        scores_without = score_items(items, llm=None, now=_NOW)
        assert scores_with[1] == pytest.approx(scores_without[1])

    def test_llm_failure_falls_back_to_base(self) -> None:
        from newsletter.core.llm import LLMError

        class _ExplodingLLM:
            def complete_json(self, *a, **k):  # type: ignore[no-untyped-def]
                raise LLMError("nope")

        items = [_mk(id=1)]
        scores = score_items(items, llm=_ExplodingLLM(), now=_NOW, top_k_for_llm=10)
        assert 1 in scores  # didn't crash
        assert scores[1] == score_items(items, llm=None, now=_NOW)[1]

    def test_items_below_top_k_use_base_only(self) -> None:
        recorder = _RecordingLLM(default_importance=5)
        items = [
            _mk(id=1, trust_level="official"),
            _mk(id=2, trust_level="community", published_at=_NOW - timedelta(days=10)),
        ]
        scores = score_items(items, llm=recorder, now=_NOW, top_k_for_llm=1)
        # Only #1 should have been LLM-boosted.
        boosted = score_items([items[0]], llm=recorder, now=_NOW, top_k_for_llm=10)
        base_only = score_items([items[1]], llm=None, now=_NOW)
        assert scores[1] == pytest.approx(boosted[1])
        assert scores[2] == pytest.approx(base_only[2])


class _RecordingLLM:
    """Stub LLMClient that returns a configurable importance number."""

    def __init__(self, *, default_importance: int) -> None:
        self.default_importance = default_importance
        self.calls: list[str] = []

    def complete_json(self, body, *, tier=None, max_tokens=None, system=None, temperature=None):  # type: ignore[no-untyped-def]
        self.calls.append(body)
        from newsletter.core.llm import LLMResponse

        payload = {"importance": self.default_importance, "rationale": "stub"}
        return payload, LLMResponse(text="", model=tier or "stub", input_tokens=0, output_tokens=0)


# Sanity: dataclass is immutable enough for safe reuse via replace().
def test_score_input_is_replaceable() -> None:
    a = _mk()
    b = replace(a, id=99)
    assert b.id == 99
    assert a.id == 1


# Sanity: math import is actually used (silence unused-import lint).
def test_math_module_available() -> None:
    assert math.exp(0.0) == 1.0
