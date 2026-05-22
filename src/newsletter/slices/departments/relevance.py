"""Pure relevance scoring for the department digest (no IO).

Two modes, chosen per run by the caller: embedding cosine when both the
department and the item carry vectors, else keyword overlap on tokens.
"""

from __future__ import annotations

from collections.abc import Sequence

from newsletter.core.embeddings import cosine
from newsletter.core.text import tokenize


def department_tokens(name: str, description: str | None) -> set[str]:
    """Lowercased token set for a department (name + description)."""
    return set(tokenize(f"{name} {description or ''}"))


def keyword_score(dept_tokens: set[str], item_text: str) -> int:
    """Count of distinct department tokens present in the item's tokens."""
    return len(dept_tokens & set(tokenize(item_text)))


def embedding_score(dept_vec: Sequence[float], item_vec: Sequence[float]) -> float:
    """Cosine similarity; 0.0 when either vector is empty."""
    if not dept_vec or not item_vec:
        return 0.0
    return cosine(dept_vec, item_vec)


__all__ = ["department_tokens", "embedding_score", "keyword_score"]
