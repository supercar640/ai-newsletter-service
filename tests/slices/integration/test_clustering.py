"""Tests for integration clustering.

Clustering groups ProcessedItem rows that report on the same underlying
story. Two signals:

1. Items already merged by the dedup pass (same ``duplicate_group_id``)
   carry that grouping forward.
2. Beyond exact dup groups, titles sharing enough keywords (Jaccard ≥
   threshold) get merged into one cluster.
"""

from __future__ import annotations

from newsletter.slices.integration.clustering import (
    ClusterInput,
    cluster_items,
    title_tokens,
)


def _mk(
    id: int,
    title: str,
    *,
    duplicate_group_id: str | None = None,
) -> ClusterInput:
    return ClusterInput(id=id, title=title, duplicate_group_id=duplicate_group_id)


class TestTitleTokens:
    def test_lowercases_and_splits(self) -> None:
        assert "openai" in title_tokens("OpenAI launches GPT-5")

    def test_drops_short_tokens(self) -> None:
        toks = title_tokens("AI is on the move")
        # 1-char tokens like "a"/"i" (if any) shouldn't slip through after
        # stopword filtering.
        for t in toks:
            assert len(t) >= 2

    def test_drops_common_stopwords(self) -> None:
        toks = title_tokens("the new model from OpenAI")
        assert "the" not in toks
        assert "from" not in toks
        assert "openai" in toks

    def test_keeps_korean_tokens(self) -> None:
        toks = title_tokens("오픈AI 신모델 공개")
        assert "오픈ai" in toks or "신모델" in toks  # depending on tokenizer

    def test_returns_set(self) -> None:
        toks = title_tokens("AI AI AI")
        assert isinstance(toks, set)


class TestClusterItems:
    def test_empty_input_is_empty(self) -> None:
        assert cluster_items([]) == {}

    def test_singleton_gets_own_cluster(self) -> None:
        result = cluster_items([_mk(1, "Anthropic releases Claude 5")])
        assert set(result.keys()) == {1}
        assert len({v for v in result.values()}) == 1

    def test_same_dup_group_clusters_together(self) -> None:
        items = [
            _mk(1, "Completely different headline", duplicate_group_id="g1"),
            _mk(2, "Another unrelated wording", duplicate_group_id="g1"),
        ]
        result = cluster_items(items)
        assert result[1] == result[2]

    def test_different_dup_groups_stay_separate(self) -> None:
        items = [
            _mk(1, "X", duplicate_group_id="g1"),
            _mk(2, "Y", duplicate_group_id="g2"),
        ]
        result = cluster_items(items)
        assert result[1] != result[2]

    def test_high_jaccard_titles_merge(self) -> None:
        # Both stories about the same GPT-5 launch from different angles.
        items = [
            _mk(1, "OpenAI launches GPT-5 flagship model"),
            _mk(2, "OpenAI announces GPT-5 flagship release"),
        ]
        result = cluster_items(items, jaccard_threshold=0.4)
        assert result[1] == result[2]

    def test_low_jaccard_titles_stay_separate(self) -> None:
        items = [
            _mk(1, "OpenAI launches GPT-5 flagship model"),
            _mk(2, "EU passes new AI safety act in Brussels"),
        ]
        result = cluster_items(items, jaccard_threshold=0.5)
        assert result[1] != result[2]

    def test_chained_titles_cluster_transitively(self) -> None:
        # a~b match strongly; b~c match strongly; a~c do not directly.
        # Union-find should still place all three in one cluster.
        items = [
            _mk(1, "OpenAI launches GPT-5 reasoning advanced model"),
            _mk(2, "GPT-5 reasoning advanced launches comparison"),
            _mk(3, "Comparison launches GPT-5 details breakdown"),
        ]
        result = cluster_items(items, jaccard_threshold=0.4)
        assert result[1] == result[2] == result[3]

    def test_dup_group_overrides_title_disagreement(self) -> None:
        # Dedupe slice already decided these are dupes — clustering must respect that.
        items = [
            _mk(1, "Foo bar baz qux", duplicate_group_id="dg"),
            _mk(2, "Zzz xxx yyy", duplicate_group_id="dg"),
        ]
        result = cluster_items(items)
        assert result[1] == result[2]

    def test_cluster_ids_are_deterministic(self) -> None:
        items = [
            _mk(1, "OpenAI launches GPT-5"),
            _mk(2, "Anthropic launches Claude 5"),
        ]
        a = cluster_items(items)
        b = cluster_items(items)
        # Same input → same id assignment (ordering doesn't matter, only
        # the partition).
        assert sorted(a.values()) == sorted(b.values())
        for k in a:
            assert a[k] == b[k]

    def test_no_dup_group_singletons(self) -> None:
        # Two clearly unrelated items with no dup group → separate clusters.
        items = [
            _mk(1, "Apple Vision Pro reviews"),
            _mk(2, "Bitcoin price surges past target"),
        ]
        result = cluster_items(items, jaccard_threshold=0.5)
        assert result[1] != result[2]

    def test_threshold_one_only_merges_identical_titles(self) -> None:
        items = [
            _mk(1, "OpenAI launches GPT-5"),
            _mk(2, "OpenAI launches GPT-5 today"),
        ]
        result = cluster_items(items, jaccard_threshold=1.0)
        assert result[1] != result[2]
