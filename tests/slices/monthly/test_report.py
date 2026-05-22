"""monthly.report — deterministic markdown rendering."""

from __future__ import annotations

from datetime import date

from newsletter.slices.competitors.schemas import (
    CompetitorMentions,
    CompetitorReport,
)
from newsletter.slices.monthly.report import render_markdown
from newsletter.slices.monthly.schemas import MonthlyReport, TopHeadline
from newsletter.slices.trends.schemas import TermDelta, TrendReport, WindowSpec


def _trend(*, rising=(), new=(), top=()) -> TrendReport:
    w = WindowSpec(
        period="month",
        current_start=date(2026, 4, 1),
        current_end=date(2026, 5, 1),
        previous_start=date(2026, 3, 1),
        previous_end=date(2026, 4, 1),
    )

    def mk(t: str) -> TermDelta:
        return TermDelta(term=t, current=3, previous=0, delta=3, importance=1.0)

    return TrendReport(
        window=w,
        rising=[mk(t) for t in rising],
        fading=[],
        new=[mk(t) for t in new],
        dropped=[],
        top_current=[mk(t) for t in top],
        total_current_items=3,
        total_previous_items=0,
    )


def _report(*, narrative=None, rising=(), competitors=(), headlines=()) -> MonthlyReport:
    return MonthlyReport(
        month="2026-04",
        since=date(2026, 4, 1),
        until=date(2026, 5, 1),
        total_items=10,
        trend=_trend(rising=rising),
        competitors=CompetitorReport(
            since=date(2026, 4, 1),
            until=date(2026, 5, 1),
            total_items=10,
            competitors=[CompetitorMentions(name=n, count=c, headlines=[]) for n, c in competitors],
        ),
        top_headlines=[
            TopHeadline(title=t, url=u, importance=1.0, category=None, summary=None)
            for t, u in headlines
        ],
        narrative=narrative,
    )


def test_header_and_sections_present():
    md = render_markdown(_report())
    assert "# 2026-04 AI 동향 리포트" in md
    assert "## 이번 달 요약" in md
    assert "## 트렌드" in md
    assert "## 경쟁사 동향" in md
    assert "## 주요 기사" in md
    assert "2026-04-01" in md and "2026-05-01" in md


def test_narrative_fallback_when_none():
    md = render_markdown(_report(narrative=None))
    assert "(요약 생략 — LLM 비활성)" in md


def test_narrative_rendered_when_present():
    md = render_markdown(_report(narrative="이번 달은 멀티모달이 화제였습니다."))
    assert "이번 달은 멀티모달이 화제였습니다." in md
    assert "(요약 생략" not in md


def test_sections_render_data_and_empty_markers():
    md = render_markdown(
        _report(
            rising=("sora", "gpt"),
            competitors=[("OpenAI", 5)],
            headlines=[("Big news", "https://e.com/a")],
        )
    )
    assert "떠오르는: sora, gpt" in md
    assert "- OpenAI: 5건" in md
    assert "[Big news](https://e.com/a)" in md

    empty = render_markdown(_report())
    assert "(데이터 없음)" in empty
    assert "(경쟁사 미등록)" in empty
    assert "(기사 없음)" in empty
