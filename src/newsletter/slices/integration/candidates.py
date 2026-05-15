"""Pick the per-track candidate list from a scored, clustered pool.

For each track we:

1. Collapse each cluster to its single highest-scored representative.
2. Sort representatives by score descending.
3. Walk the sorted list and admit candidates up to the per-track cap,
   respecting ``max_per_category`` for diversity.
4. If we run out of fresh categories before filling the slot, optionally
   relax the cap — better to ship a few same-category items than a
   half-empty newsletter (unless the caller asks for strict enforcement).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

_EXPERT_DEFAULT: Final = 7
_PRACTICAL_DEFAULT: Final = 4
_MAX_PER_CATEGORY_DEFAULT: Final = 2

TRACKS: Final = ("expert_news", "practical_insight")


@dataclass(slots=True, frozen=True)
class CandidateInput:
    """One scored, clustered ProcessedItem ready for selection."""

    id: int
    track: str
    category: str | None
    cluster_id: str
    score: float


@dataclass(slots=True, frozen=True)
class Candidate:
    """The chosen representative of a cluster within a track."""

    id: int
    track: str
    category: str | None
    cluster_id: str
    score: float
    cluster_member_ids: tuple[int, ...]


def select_candidates(
    inputs: list[CandidateInput],
    *,
    expert_count: int = _EXPERT_DEFAULT,
    practical_count: int = _PRACTICAL_DEFAULT,
    max_per_category: int = _MAX_PER_CATEGORY_DEFAULT,
    enforce_diversity_strict: bool = False,
) -> dict[str, list[Candidate]]:
    """Return ``{track: [Candidate, ...]}`` per track.

    Parameters
    ----------
    expert_count, practical_count:
        Maximum number of candidates to return per track.
    max_per_category:
        Soft cap on items sharing the same category. ``None``-category
        items are treated as their own bucket so they never block other
        categories.
    enforce_diversity_strict:
        When ``True``, the category cap is a hard limit (output may be
        shorter than ``expert_count``). When ``False`` (default), the
        selector falls back to over-cap items rather than ship too few.
    """
    by_track = {t: [it for it in inputs if it.track == t] for t in TRACKS}
    counts = {
        "expert_news": expert_count,
        "practical_insight": practical_count,
    }
    return {
        track: _select_for_track(
            by_track[track],
            limit=counts[track],
            max_per_category=max_per_category,
            enforce_diversity_strict=enforce_diversity_strict,
        )
        for track in TRACKS
    }


def _select_for_track(
    inputs: list[CandidateInput],
    *,
    limit: int,
    max_per_category: int,
    enforce_diversity_strict: bool,
) -> list[Candidate]:
    if not inputs or limit <= 0:
        return []

    reps = _cluster_representatives(inputs)
    reps.sort(key=lambda c: (-c.score, c.id))

    chosen: list[Candidate] = []
    deferred: list[Candidate] = []
    seen_categories: dict[str, int] = {}

    for cand in reps:
        if len(chosen) >= limit:
            break
        key = _category_key(cand.category)
        # None-category items skip the diversity cap; otherwise enforce.
        if cand.category is not None and seen_categories.get(key, 0) >= max_per_category:
            deferred.append(cand)
            continue
        chosen.append(cand)
        seen_categories[key] = seen_categories.get(key, 0) + 1

    if not enforce_diversity_strict and len(chosen) < limit and deferred:
        for cand in deferred:
            if len(chosen) >= limit:
                break
            chosen.append(cand)

    return chosen


def _cluster_representatives(inputs: list[CandidateInput]) -> list[Candidate]:
    """One Candidate per cluster — the highest-scored item, plus its members."""
    by_cluster: dict[str, list[CandidateInput]] = {}
    for item in inputs:
        by_cluster.setdefault(item.cluster_id, []).append(item)

    reps: list[Candidate] = []
    for cluster_id, members in by_cluster.items():
        members_sorted = sorted(members, key=lambda i: (-i.score, i.id))
        top = members_sorted[0]
        member_ids = tuple(sorted(m.id for m in members))
        reps.append(
            Candidate(
                id=top.id,
                track=top.track,
                category=top.category,
                cluster_id=cluster_id,
                score=top.score,
                cluster_member_ids=member_ids,
            )
        )
    return reps


def _category_key(category: str | None) -> str:
    return category if category is not None else ""


__all__ = ["TRACKS", "Candidate", "CandidateInput", "select_candidates"]
