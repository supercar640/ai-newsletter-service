"""Track classification: expert_news vs practical_insight vs both.

The source's declared ``content_track`` is the strong prior — a source
the admin tagged ``practical_insight`` usually really is practical. We
only call the LLM when the source declared ``both``, since that's the
only case where the per-item track actually needs deciding.
"""

from __future__ import annotations

from typing import Final

from newsletter.core.llm import LLMClient, LLMError
from newsletter.core.logging import get_logger
from newsletter.core.prompts import load_prompt
from newsletter.models.source import Source

log = get_logger(__name__)

_VALID_TRACKS: Final = frozenset({"expert_news", "practical_insight", "both"})


def classify(
    source: Source,
    title: str,
    summary: str | None,
    *,
    llm: LLMClient | None = None,
) -> str:
    """Return the per-item track ('expert_news' or 'practical_insight').

    If the source has a fixed track, return it. If the source is 'both'
    and an LLM is available, ask. Otherwise default to 'expert_news'.
    """
    declared = (source.content_track or "").strip()
    if declared in {"expert_news", "practical_insight"}:
        return declared

    if declared != "both" or llm is None:
        return "expert_news"

    return _llm_classify(title, summary, llm=llm)


def _llm_classify(title: str, summary: str | None, *, llm: LLMClient) -> str:
    prompt = load_prompt("common/track-classifier.md")
    try:
        payload, _ = llm.complete_json(
            prompt.render(title=title or "(no title)", summary=(summary or "")[:600]),
            tier=prompt.tier,
            max_tokens=128,
        )
    except LLMError as exc:
        log.warning("track.llm_failed", error=str(exc))
        return "expert_news"

    raw = str(payload.get("track", "expert_news")).strip()
    if raw not in {"expert_news", "practical_insight"}:
        return "expert_news"
    return raw
