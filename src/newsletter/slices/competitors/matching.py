"""Pure alias matching for competitor detection (no IO).

ASCII aliases match on word boundaries so "meta" does not match
"metadata". The search uses ``re.ASCII`` so that Korean particles (를, 의, 가,
…) are treated as non-word characters and therefore act as word boundaries —
without the flag, Python's Unicode ``\\w`` would include Korean characters and
swallow the boundary, silently missing matches like "gpt를 사용한다".

Non-ASCII aliases (Korean, etc.) match as substrings because
Korean particles attach with no whitespace boundary, making ``\\b`` unusable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompetitorProfile:
    """An enabled competitor reduced to what matching needs.

    ``aliases`` are already lowercased by the caller.
    """

    id: int
    name: str
    aliases: tuple[str, ...]


def alias_matches(text_lower: str, alias_lower: str) -> bool:
    """True if ``alias_lower`` occurs in the already-lowercased ``text_lower``."""
    if not alias_lower:
        return False
    if alias_lower.isascii():
        return re.search(rf"\b{re.escape(alias_lower)}\b", text_lower, re.ASCII) is not None
    return alias_lower in text_lower


def mentioned_competitor_ids(text_lower: str, competitors: list[CompetitorProfile]) -> set[int]:
    """Ids of competitors with any alias present in the text."""
    return {c.id for c in competitors if any(alias_matches(text_lower, a) for a in c.aliases)}


__all__ = ["CompetitorProfile", "alias_matches", "mentioned_competitor_ids"]
