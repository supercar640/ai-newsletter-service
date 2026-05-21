"""Output shapes for trend analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class WindowSpec:
    period: str          # "week" | "month"
    current_start: date
    current_end: date    # exclusive
    previous_start: date
    previous_end: date   # exclusive (== current_start)


@dataclass(frozen=True, slots=True)
class TermDelta:
    term: str
    current: int         # article count this window
    previous: int        # article count prior window
    delta: int           # current - previous
    importance: float    # sum of importance_score this window (tiebreak)


@dataclass(frozen=True, slots=True)
class TrendBuckets:
    rising: list[TermDelta]
    fading: list[TermDelta]
    new: list[TermDelta]
    dropped: list[TermDelta]
    top_current: list[TermDelta]


@dataclass(frozen=True, slots=True)
class TrendReport:
    window: WindowSpec
    rising: list[TermDelta]
    fading: list[TermDelta]
    new: list[TermDelta]
    dropped: list[TermDelta]
    top_current: list[TermDelta]
    total_current_items: int
    total_previous_items: int


__all__ = ["TermDelta", "TrendBuckets", "TrendReport", "WindowSpec"]
