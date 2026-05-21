"""Pure text chunking + keyword extraction for the company-context corpus.

No IO, no DB. The indexer wires these helpers to the filesystem and the
embedding client. Splitting is deterministic so re-indexing an unchanged
file yields identical chunks.
"""

from __future__ import annotations

import re
from collections import Counter

_HEADING_LINE_RE = re.compile(r"^#{1,6}\s")
_TOKEN_RE = re.compile(r"[0-9a-z가-힣]+")

# Light stopword set — common English glue words + Korean particles/fillers.
# Single-character tokens are dropped separately, so only len>1 entries matter.
_STOPWORDS = frozenset(
    {
        "the", "and", "for", "are", "but", "not", "you", "with", "this",
        "that", "from", "have", "was", "were", "한다", "합니다", "있다",
        "있습니다", "그리고", "그러나", "또는", "등의", "대한", "위한",
    }
)


def chunk_text(text: str, *, max_chars: int = 1200) -> list[str]:
    """Split a document into chunks at headings/paragraphs, capped at max_chars."""
    if max_chars < 1:
        raise ValueError(f"max_chars must be >= 1, got {max_chars}")
    blocks: list[str] = []
    for block in _split_blocks(text):
        blocks.extend(_hard_split(block, max_chars))

    chunks: list[str] = []
    current = ""
    for block in blocks:
        starts_new_section = bool(_HEADING_LINE_RE.match(block))
        if not current:
            current = block
        elif not starts_new_section and len(current) + 2 + len(block) <= max_chars:
            current = f"{current}\n\n{block}"
        else:
            chunks.append(current)
            current = block
    if current.strip():
        chunks.append(current)
    return [c.strip() for c in chunks if c.strip()]


def extract_keywords(text: str, *, max_keywords: int = 20) -> list[str]:
    """Frequency-ranked lowercased tokens. Deterministic (alpha tie-break)."""
    tokens = _TOKEN_RE.findall(text.lower())
    counts = Counter(t for t in tokens if len(t) > 1 and t not in _STOPWORDS)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [token for token, _ in ranked[:max_keywords]]


def _split_blocks(text: str) -> list[str]:
    """Break text on heading lines and blank-line paragraph boundaries."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            joined = "\n".join(buffer).strip()
            if joined:
                blocks.append(joined)
            buffer.clear()

    for line in normalized.split("\n"):
        if _HEADING_LINE_RE.match(line):
            flush()
            buffer.append(line)
        elif line.strip() == "":
            flush()
        else:
            buffer.append(line)
    flush()
    return blocks


def _hard_split(block: str, max_chars: int) -> list[str]:
    """Split an oversize block on whitespace; chop any single oversize word."""
    if len(block) <= max_chars:
        return [block]
    pieces: list[str] = []
    current = ""
    for word in block.split(" "):
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current = f"{current} {word}"
        else:
            pieces.append(current)
            current = word
    if current:
        pieces.append(current)

    result: list[str] = []
    for piece in pieces:
        while len(piece) > max_chars:
            result.append(piece[:max_chars])
            piece = piece[max_chars:]
        if piece:
            result.append(piece)
    return result


__all__ = ["chunk_text", "extract_keywords"]
