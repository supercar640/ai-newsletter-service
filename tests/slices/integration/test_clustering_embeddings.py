"""Embedding-aware clustering (Phase 2)."""

from __future__ import annotations

from newsletter.slices.integration.clustering import ClusterInput, cluster_items


def _mk(id: int, title: str, *, duplicate_group_id: str | None = None) -> ClusterInput:
    return ClusterInput(id=id, title=title, duplicate_group_id=duplicate_group_id)


def test_high_cosine_merges_even_with_disjoint_titles():
    """The whole point of embeddings: two stories about the same event
    written with different vocabularies should cluster."""
    items = [
        _mk(1, "오픈AI, 새 추론 모델 발표"),
        _mk(2, "OpenAI debuts new reasoning model GPT-5"),
    ]
    embeddings = {
        1: [1.0, 0.0, 0.0],
        2: [0.98, 0.2, 0.0],  # cos ≈ 0.98
    }
    result = cluster_items(items, embeddings=embeddings, cosine_threshold=0.85)
    assert result[1] == result[2]


def test_low_cosine_stays_separate_even_if_some_tokens_overlap():
    """Same word ('AI') shared, but stories are unrelated semantically."""
    items = [
        _mk(1, "AI startup raises $50M Series A"),
        _mk(2, "AI regulation bill passes EU parliament"),
    ]
    embeddings = {
        1: [1.0, 0.0, 0.0],
        2: [0.0, 1.0, 0.0],  # cos = 0
    }
    result = cluster_items(items, embeddings=embeddings, cosine_threshold=0.85)
    assert result[1] != result[2]


def test_falls_back_to_jaccard_when_one_side_lacks_embedding():
    items = [
        _mk(1, "OpenAI launches GPT-5 flagship model"),
        _mk(2, "OpenAI announces GPT-5 flagship release"),
    ]
    embeddings = {1: [1.0, 0.0, 0.0]}  # only item 1 has a vector
    result = cluster_items(items, embeddings=embeddings, jaccard_threshold=0.4)
    # Jaccard handles this pair.
    assert result[1] == result[2]


def test_embeddings_none_preserves_jaccard_behavior():
    items = [
        _mk(1, "OpenAI launches GPT-5 reasoning model"),
        _mk(2, "OpenAI announces GPT-5 reasoning model"),
    ]
    a = cluster_items(items, jaccard_threshold=0.4)
    b = cluster_items(items, jaccard_threshold=0.4, embeddings=None)
    assert a == b


def test_embedding_only_pair_does_not_clobber_jaccard_threshold():
    """If cosine is below threshold and Jaccard is above, items still merge."""
    items = [
        _mk(1, "OpenAI launches GPT-5 flagship model"),
        _mk(2, "OpenAI announces GPT-5 flagship release"),
    ]
    # Cosine = 0 (orthogonal), Jaccard 4/6 ≈ 0.67.
    embeddings = {
        1: [1.0, 0.0, 0.0],
        2: [0.0, 1.0, 0.0],
    }
    result = cluster_items(
        items,
        embeddings=embeddings,
        jaccard_threshold=0.4,
        cosine_threshold=0.85,
    )
    assert result[1] == result[2]


def test_transitive_clustering_through_embedding_chain():
    items = [
        _mk(1, "오픈AI 추론 모델"),
        _mk(2, "OpenAI debuts reasoning model"),
        _mk(3, "GPT-5 reasoning unveiled"),
    ]
    # cos(1,2)≈0.95, cos(2,3)≈0.94, cos(1,3)≈0.78 (below threshold).
    # Union-find still places all three in one cluster via the chain.
    embeddings = {
        1: [1.0, 0.0, 0.0],
        2: [0.95, 0.31, 0.0],
        3: [0.78, 0.625, 0.0],
    }
    result = cluster_items(items, embeddings=embeddings, cosine_threshold=0.85)
    assert result[1] == result[2] == result[3]
