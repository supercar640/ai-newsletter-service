"""Schemas for the monthly AI digest report."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from newsletter.slices.competitors.schemas import CompetitorReport
from newsletter.slices.trends.schemas import TrendReport


@dataclass(frozen=True, slots=True)
class TopHeadline:
    """One importance-ranked article in the digest's 주요 기사 section."""

    title: str
    url: str
    importance: float
    category: str | None
    summary: str | None  # used only as LLM narrative input, not rendered


@dataclass(frozen=True, slots=True)
class MonthlyReport:
    """Aggregated month of data plus an optional LLM narrative."""

    month: str  # "2026-04"
    since: date
    until: date  # exclusive (first day of next month)
    total_items: int
    trend: TrendReport
    competitors: CompetitorReport
    top_headlines: list[TopHeadline]  # importance desc, truncated to top_k
    narrative: str | None = None
