"""Output shapes for the corpus slice."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class IndexReport:
    """Summary of one ``index_corpus`` run."""

    scanned: int = 0
    indexed: int = 0
    skipped: int = 0
    chunks: int = 0
    embedded: int = 0


__all__ = ["IndexReport"]
