"""Cluster ProcessedItems that report the same underlying story.

Seeds the cluster partition with each item's ``duplicate_group_id`` (set
by the processing slice). The pairwise merge pass uses cosine similarity
on Voyage embeddings when both items have one — falling back to title-
token Jaccard when at least one side is missing an embedding so semantic
clustering rolls out incrementally without blocking existing pipelines.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from newsletter.core.embeddings import cosine

_TOKEN_RE: Final = re.compile(
    r"[A-Za-z0-9가-힣ぁ-んァ-ン一-龯][\w가-힣ぁ-んァ-ン一-龯-]*", re.UNICODE
)
_MIN_TOKEN_LEN: Final = 2

# Short, opinionated stopword list. Anything ambiguous stays in — clustering
# is permissive and downstream candidate selection trims noise.
_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "of",
        "to",
        "in",
        "on",
        "at",
        "for",
        "by",
        "with",
        "and",
        "or",
        "but",
        "from",
        "into",
        "as",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "so",
    }
)


@dataclass(slots=True, frozen=True)
class ClusterInput:
    """Minimum data needed to place an item in a cluster."""

    id: int
    title: str
    duplicate_group_id: str | None


def title_tokens(title: str) -> set[str]:
    """Lowercase + tokenize + drop stopwords / 1-char tokens."""
    if not title:
        return set()
    raw = _TOKEN_RE.findall(title.lower())
    return {t for t in raw if len(t) >= _MIN_TOKEN_LEN and t not in _STOPWORDS}


def cluster_items(
    items: list[ClusterInput],
    *,
    jaccard_threshold: float = 0.5,
    embeddings: Mapping[int, Sequence[float]] | None = None,
    cosine_threshold: float = 0.85,
) -> dict[int, str]:
    """Return ``{item.id: cluster_id}`` for every input item.

    Two items end up in the same cluster when any of these hold:
    * they share a ``duplicate_group_id`` (set by the dedupe pass)
    * both have an embedding and their cosine similarity is at or above
      ``cosine_threshold``
    * their title-token Jaccard is at or above ``jaccard_threshold``
      (always evaluated — semantic and lexical merge unions, not gates)

    Merges are transitive (union-find), so chained matches connect the
    full component.
    """
    if not items:
        return {}

    parent: dict[int, int] = {item.id: item.id for item in items}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        # Deterministic: smaller id becomes the root so cluster ids stay stable.
        if ra < rb:
            parent[rb] = ra
        else:
            parent[ra] = rb

    # Pass 1: merge by duplicate_group_id.
    by_group: dict[str, list[int]] = {}
    for item in items:
        if item.duplicate_group_id:
            by_group.setdefault(item.duplicate_group_id, []).append(item.id)
    for ids in by_group.values():
        first = ids[0]
        for other in ids[1:]:
            union(first, other)

    # Pass 2: merge by semantic cosine (when both sides have a vector)
    # OR by title-token Jaccard. O(n^2) is fine for MVP volume
    # (tens to a couple hundred items per run).
    tokens = {item.id: title_tokens(item.title) for item in items}
    embeds = embeddings or {}
    ids_sorted = sorted(parent.keys())
    for i, a in enumerate(ids_sorted):
        for b in ids_sorted[i + 1 :]:
            if find(a) == find(b):
                continue
            ea = embeds.get(a)
            eb = embeds.get(b)
            if ea is not None and eb is not None and cosine(ea, eb) >= cosine_threshold:
                union(a, b)
                continue
            if _jaccard(tokens[a], tokens[b]) >= jaccard_threshold:
                union(a, b)

    # Materialize cluster ids — derived from root id so the same input
    # yields the same assignment across runs.
    return {item_id: _cluster_id(find(item_id)) for item_id in parent}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _cluster_id(root: int) -> str:
    """Stable cluster id derived from the partition's root id."""
    return "c" + hashlib.sha1(str(root).encode("ascii")).hexdigest()[:10]


__all__ = ["ClusterInput", "cluster_items", "title_tokens"]
