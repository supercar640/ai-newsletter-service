"""Schemas for the performance dashboard report."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class SourceStat:
    """Per-source yield and average quality within the window."""

    source_id: str
    name: str
    content_track: str
    collected: int
    processed: int
    avg_relevance: float  # 0.0 when processed == 0
    avg_importance: float


@dataclass(frozen=True, slots=True)
class QualitySummary:
    """Window-wide quality rollup."""

    total_collected: int
    total_processed: int
    track_counts: dict[str, int]  # content_track -> processed count
    top_categories: list[tuple[str, int]]  # (category, count) desc, top_k
    distinct_groups: int  # distinct non-null duplicate_group_id
    grouped_items: int  # processed items carrying a duplicate_group_id


@dataclass(frozen=True, slots=True)
class DashboardReport:
    since: date
    until: date  # exclusive
    sources: list[SourceStat]  # collected desc, then name
    quality: QualitySummary
