"""dashboard.report — deterministic markdown rendering."""

from __future__ import annotations

from datetime import date

from newsletter.slices.dashboard.report import render_markdown
from newsletter.slices.dashboard.schemas import (
    DashboardReport,
    QualitySummary,
    SourceStat,
)


def _report(*, sources=(), quality=None) -> DashboardReport:
    return DashboardReport(
        since=date(2026, 5, 15),
        until=date(2026, 5, 22),
        sources=list(sources),
        quality=quality
        or QualitySummary(
            total_collected=0,
            total_processed=0,
            track_counts={},
            top_categories=[],
            distinct_groups=0,
            grouped_items=0,
        ),
    )


def test_header_period():
    md = render_markdown(_report())
    assert "# 성과 대시보드" in md
    assert "2026-05-15" in md and "2026-05-22" in md


def test_source_table_rendered():
    s = SourceStat(
        source_id="src",
        name="My Source",
        content_track="expert_news",
        collected=10,
        processed=7,
        avg_relevance=0.83,
        avg_importance=2.5,
    )
    md = render_markdown(_report(sources=[s]))
    assert "## 소스별 성과" in md
    assert "My Source" in md
    assert "| My Source | expert_news | 10 | 7 | 0.83 | 2.50 |" in md


def test_quality_summary_rendered():
    q = QualitySummary(
        total_collected=20,
        total_processed=12,
        track_counts={"expert_news": 8, "practical_insight": 4},
        top_categories=[("LLM", 5), ("Tooling", 3)],
        distinct_groups=2,
        grouped_items=6,
    )
    md = render_markdown(_report(quality=q))
    assert "전체 수집: 20건 / 처리: 12건" in md
    assert "expert_news: 8" in md and "practical_insight: 4" in md
    assert "그룹화 6건 / 고유 그룹 2개" in md
    assert "| LLM | 5 |" in md


def test_empty_markers():
    md = render_markdown(_report())
    assert "(데이터 없음)" in md
    assert "(없음)" in md
