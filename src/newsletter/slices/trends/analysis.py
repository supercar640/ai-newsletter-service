"""Pure trend classification: compare two term-frequency windows."""

from __future__ import annotations

from newsletter.slices.trends.schemas import TermDelta, TrendBuckets


def compare_windows(
    current: dict[str, int],
    previous: dict[str, int],
    *,
    importance: dict[str, float],
    top_n: int = 15,
    min_count: int = 2,
) -> TrendBuckets:
    """Classify terms into rising/fading/new/dropped/top_current buckets.

    ``current``/``previous`` map term -> article count. ``importance`` maps
    term -> summed importance_score this window (used only as a tiebreak).
    Terms below ``min_count`` in the relevant window are dropped as noise.
    Each bucket is truncated to ``top_n``.
    """
    rising: list[TermDelta] = []
    fading: list[TermDelta] = []
    new: list[TermDelta] = []
    dropped: list[TermDelta] = []

    for term in set(current) | set(previous):
        c = current.get(term, 0)
        p = previous.get(term, 0)
        delta = TermDelta(
            term=term,
            current=c,
            previous=p,
            delta=c - p,
            importance=importance.get(term, 0.0),
        )
        if p == 0 and c >= min_count:
            new.append(delta)
        elif c == 0 and p >= min_count:
            dropped.append(delta)
        elif c > p > 0 and c >= min_count:
            rising.append(delta)
        elif 0 < c < p and p >= min_count:
            fading.append(delta)

    rising.sort(key=lambda d: (-d.delta, -d.importance, d.term))
    new.sort(key=lambda d: (-d.current, -d.importance, d.term))
    fading.sort(key=lambda d: (d.delta, -d.importance, d.term))
    dropped.sort(key=lambda d: (-d.previous, d.term))

    top_current = sorted(
        (
            TermDelta(
                term=term,
                current=c,
                previous=previous.get(term, 0),
                delta=c - previous.get(term, 0),
                importance=importance.get(term, 0.0),
            )
            for term, c in current.items()
            if c >= min_count
        ),
        key=lambda d: (-d.current, -d.importance, d.term),
    )

    return TrendBuckets(
        rising=rising[:top_n],
        fading=fading[:top_n],
        new=new[:top_n],
        dropped=dropped[:top_n],
        top_current=top_current[:top_n],
    )


__all__ = ["compare_windows"]
