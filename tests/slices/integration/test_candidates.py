"""Tests for candidate selection."""

from __future__ import annotations

from newsletter.slices.integration.candidates import (
    CandidateInput,
    select_candidates,
)


def _mk(
    id: int,
    *,
    track: str = "expert_news",
    category: str | None = "AI Model",
    cluster_id: str | None = None,
    score: float = 0.5,
) -> CandidateInput:
    return CandidateInput(
        id=id,
        track=track,
        category=category,
        cluster_id=cluster_id or f"c{id:03d}",
        score=score,
    )


class TestCandidateSelectionBasics:
    def test_empty_returns_empty_tracks(self) -> None:
        result = select_candidates([])
        assert result["expert_news"] == []
        assert result["practical_insight"] == []

    def test_splits_by_track(self) -> None:
        inputs = [
            _mk(1, track="expert_news"),
            _mk(2, track="practical_insight"),
            _mk(3, track="expert_news"),
        ]
        result = select_candidates(inputs)
        assert {c.id for c in result["expert_news"]} == {1, 3}
        assert {c.id for c in result["practical_insight"]} == {2}

    def test_returns_at_most_expert_count(self) -> None:
        inputs = [_mk(i, score=float(i) / 100) for i in range(1, 20)]
        result = select_candidates(inputs, expert_count=5)
        assert len(result["expert_news"]) == 5

    def test_returns_at_most_practical_count(self) -> None:
        inputs = [_mk(i, track="practical_insight", score=float(i) / 100) for i in range(1, 10)]
        result = select_candidates(inputs, practical_count=3)
        assert len(result["practical_insight"]) == 3

    def test_higher_score_picked_first(self) -> None:
        inputs = [
            _mk(1, score=0.1),
            _mk(2, score=0.9),
            _mk(3, score=0.5),
        ]
        result = select_candidates(inputs, expert_count=2)
        ids = [c.id for c in result["expert_news"]]
        assert ids[0] == 2
        assert ids[1] == 3


class TestClusterReduction:
    def test_one_candidate_per_cluster(self) -> None:
        # Two items in the same cluster — only the higher-scored survives.
        inputs = [
            _mk(1, cluster_id="cA", score=0.4),
            _mk(2, cluster_id="cA", score=0.8),
            _mk(3, cluster_id="cB", score=0.6),
        ]
        result = select_candidates(inputs, expert_count=5)
        ids = [c.id for c in result["expert_news"]]
        assert 1 not in ids
        assert 2 in ids and 3 in ids

    def test_candidate_carries_cluster_member_ids(self) -> None:
        inputs = [
            _mk(1, cluster_id="cA", score=0.4),
            _mk(2, cluster_id="cA", score=0.8),
            _mk(3, cluster_id="cA", score=0.5),
        ]
        result = select_candidates(inputs, expert_count=1)
        cand = result["expert_news"][0]
        assert cand.id == 2
        assert set(cand.cluster_member_ids) == {1, 2, 3}

    def test_singleton_cluster_member_is_itself(self) -> None:
        result = select_candidates([_mk(1, cluster_id="solo")], expert_count=1)
        cand = result["expert_news"][0]
        assert cand.cluster_member_ids == (1,)


class TestCategoryDiversity:
    def test_caps_per_category(self) -> None:
        # All 5 inputs share a category. max_per_category=2 should clip the
        # output to 2 even though expert_count=5.
        inputs = [_mk(i, category="AI Model", score=1.0 - i * 0.1) for i in range(1, 6)]
        result = select_candidates(
            inputs, expert_count=5, max_per_category=2, enforce_diversity_strict=True
        )
        assert len(result["expert_news"]) == 2

    def test_prefers_diverse_categories(self) -> None:
        # Two high-scoring 'AI Model' items + one lower 'Policy' item. With
        # max_per_category=1, we expect the top AI Model + the Policy item
        # ahead of the second AI Model.
        inputs = [
            _mk(1, category="AI Model", score=0.9),
            _mk(2, category="AI Model", score=0.85),
            _mk(3, category="Policy", score=0.4),
        ]
        result = select_candidates(inputs, expert_count=2, max_per_category=1)
        ids = [c.id for c in result["expert_news"]]
        assert ids == [1, 3]

    def test_overflow_when_no_diverse_options_left(self) -> None:
        # Only one category present, cap=1, but expert_count=3.
        # Without strict enforcement, we relax the cap rather than return
        # too few — better to ship 3 same-category items than 1.
        inputs = [_mk(i, category="AI Model", score=1.0 - i * 0.1) for i in range(1, 4)]
        result = select_candidates(
            inputs, expert_count=3, max_per_category=1, enforce_diversity_strict=False
        )
        assert len(result["expert_news"]) == 3

    def test_unknown_category_counts_as_diverse(self) -> None:
        # Items with category=None should not all be lumped together;
        # treat None as its own bucket but never block other slots.
        inputs = [
            _mk(1, category=None, score=0.9),
            _mk(2, category=None, score=0.8),
            _mk(3, category="Research", score=0.7),
        ]
        result = select_candidates(inputs, expert_count=3, max_per_category=2)
        ids = {c.id for c in result["expert_news"]}
        assert ids == {1, 2, 3}


class TestTracksAreIndependent:
    def test_expert_count_doesnt_affect_practical(self) -> None:
        inputs = [
            _mk(1, track="expert_news", score=0.9),
            _mk(2, track="expert_news", score=0.8),
            _mk(3, track="practical_insight", score=0.7),
            _mk(4, track="practical_insight", score=0.6),
        ]
        result = select_candidates(inputs, expert_count=1, practical_count=2)
        assert len(result["expert_news"]) == 1
        assert len(result["practical_insight"]) == 2

    def test_same_cluster_across_tracks_separate(self) -> None:
        # A 'both'-classified cluster could span tracks; selection should
        # still output independent winners per track.
        inputs = [
            _mk(1, track="expert_news", cluster_id="cX", score=0.9),
            _mk(2, track="practical_insight", cluster_id="cX", score=0.6),
        ]
        result = select_candidates(inputs)
        assert len(result["expert_news"]) == 1
        assert len(result["practical_insight"]) == 1
