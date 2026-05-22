"""competitors.report — deterministic markdown rendering."""

from __future__ import annotations

from datetime import date

from newsletter.slices.competitors.report import render_markdown
from newsletter.slices.competitors.schemas import (
    CompetitorMentions,
    CompetitorReport,
    Headline,
)


def _report(competitors):
    return CompetitorReport(
        since=date(2026, 5, 15),
        until=date(2026, 5, 22),
        total_items=42,
        competitors=competitors,
    )


def test_header_includes_window_and_scan_count():
    md = render_markdown(_report([]))
    assert "2026-05-15" in md
    assert "2026-05-22" in md
    assert "42" in md


def test_competitor_counts_and_headlines_in_importance_order():
    mentions = CompetitorMentions(
        name="OpenAI",
        count=2,
        headlines=[
            Headline(title="Top story", url="https://e.com/a", importance=3.0),
            Headline(title="Lesser story", url="https://e.com/b", importance=1.0),
        ],
    )
    md = render_markdown(_report([mentions]))
    assert "## OpenAI — 2건" in md
    assert "[Top story](https://e.com/a)" in md
    # importance order: top story precedes lesser story in the text
    assert md.index("Top story") < md.index("Lesser story")


def test_zero_count_competitor_shows_no_mention_marker():
    mentions = CompetitorMentions(name="Cohere", count=0, headlines=[])
    md = render_markdown(_report([mentions]))
    assert "## Cohere — 0건" in md
    assert "(언급 없음)" in md
