"""LLM narrative ("이번 달 요약") for the monthly digest.

Feeds the deterministic digest (top terms, competitor mention counts, top
headline titles + truncated summaries) to the writer model and returns prose
markdown. Title + truncated summary only — never full article bodies. Returns
``None`` when the LLM is unavailable so the rest of the report still renders.
"""

from __future__ import annotations

import json
from typing import Any

from newsletter.core.llm import LLMClient, LLMError
from newsletter.core.logging import get_logger
from newsletter.core.prompts import load_prompt
from newsletter.slices.monthly.schemas import MonthlyReport

log = get_logger(__name__)

_PROMPT = "monthly/digest-narrative.md"
_SUMMARY_CHARS = 300


def build_narrative(report: MonthlyReport, *, llm: LLMClient) -> str | None:
    """Generate the Korean narrative section, or ``None`` if the LLM fails."""
    prompt = load_prompt(_PROMPT)
    digest_json = json.dumps(_digest_input(report), ensure_ascii=False)
    body = prompt.render(month=report.month, digest_json=digest_json)
    try:
        response = llm.complete(body, tier=prompt.tier, max_tokens=2048)
    except LLMError as exc:
        log.warning("monthly.narrative.failed", error=str(exc))
        return None
    return response.text.strip() or None


def _digest_input(report: MonthlyReport) -> dict[str, Any]:
    return {
        "rising_terms": [d.term for d in report.trend.rising[:10]],
        "new_terms": [d.term for d in report.trend.new[:10]],
        "competitors": [{"name": m.name, "count": m.count} for m in report.competitors.competitors],
        "top_headlines": [
            {
                "title": h.title,
                "category": h.category,
                "summary": (h.summary or "")[:_SUMMARY_CHARS],
            }
            for h in report.top_headlines
        ],
    }


__all__ = ["build_narrative"]
