"""Pure title → distinct-terms mapping for trend analysis."""

from __future__ import annotations

from newsletter.core.text import tokenize


def title_terms(title: str) -> set[str]:
    """Distinct terms in one title (per-article dedup)."""
    return set(tokenize(title))


__all__ = ["title_terms"]
