"""Shared lowercased word tokenization used by the corpus + trends slices.

Pure, deterministic, no IO. Lowercases input, extracts word tokens, and drops
length-1 tokens and a light stopword set.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[0-9a-z가-힣]+")

# Light stopword set — common English glue words + Korean particles/fillers.
# Single-character tokens are dropped separately, so only len>1 entries matter.
STOPWORDS = frozenset(
    {
        "the", "and", "for", "are", "but", "not", "you", "with", "this",
        "that", "from", "have", "was", "were", "한다", "합니다", "있다",
        "있습니다", "그리고", "그러나", "또는", "등의", "대한", "위한",
    }
)


def tokenize(text: str) -> list[str]:
    """Lowercased word tokens, dropping length-1 tokens and stopwords."""
    return [
        t
        for t in _TOKEN_RE.findall(text.lower())
        if len(t) > 1 and t not in STOPWORDS
    ]


__all__ = ["STOPWORDS", "tokenize"]
