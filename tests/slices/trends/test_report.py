"""trends.report — deterministic markdown rendering."""

from __future__ import annotations

from datetime import date

from newsletter.slices.trends.report import render_markdown
from newsletter.slices.trends.schemas import TermDelta, TrendReport, WindowSpec

_SPEC = WindowSpec(
    period="week",
    current_start=date(2026, 5, 15),
    current_end=date(2026, 5, 22),
    previous_start=date(2026, 5, 8),
    previous_end=date(2026, 5, 15),
)


def _report(**kw) -> TrendReport:
    base = dict(
        window=_SPEC,
        rising=[],
        fading=[],
        new=[],
        dropped=[],
        top_current=[],
        total_current_items=0,
        total_previous_items=0,
    )
    base.update(kw)
    return TrendReport(**base)


def test_render_includes_period_and_dates():
    md = render_markdown(_report(total_current_items=5, total_previous_items=3))
    assert "week" in md
    assert "2026-05-15" in md
    assert "2026-05-22" in md


def test_render_lists_rising_terms():
    rising = [TermDelta(term="rag", current=8, previous=3, delta=5, importance=0.0)]
    md = render_markdown(_report(rising=rising))
    assert "rag" in md
    assert "5" in md  # delta


def test_render_empty_sections_marked():
    md = render_markdown(_report())
    assert "(없음)" in md
