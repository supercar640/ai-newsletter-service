"""AI-relevance filtering.

Two stages:

1. **Keyword whitelist** — cheap, always-applied. Any item whose
   title/summary mentions a known AI term is admitted immediately with
   a high deterministic score.
2. **LLM classifier** — invoked only for items that pass keyword filter
   but are ambiguous, OR for sources whose ``content_track`` requires
   semantic confirmation. Returns ``{"is_ai_related": bool, "confidence": 0..1}``.

The keyword list is intentionally broad — false positives are cheaper
than missed AI stories at this stage. Track classification and
importance scoring downstream will weed out noise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from newsletter.core.llm import LLMClient, LLMError
from newsletter.core.logging import get_logger
from newsletter.core.prompts import load_prompt

log = get_logger(__name__)

_AI_KEYWORDS: tuple[str, ...] = (
    "AI",
    "A.I.",
    "인공지능",
    "생성형",
    "생성 AI",
    "거대언어",
    "거대 언어",
    "머신러닝",
    "machine learning",
    "딥러닝",
    "deep learning",
    "LLM",
    "large language model",
    "GPT",
    "ChatGPT",
    "Claude",
    "Gemini",
    "Llama",
    "Anthropic",
    "OpenAI",
    "DeepMind",
    "Hugging Face",
    "stable diffusion",
    "Midjourney",
    "Copilot",
    "RAG",
    "agent",
    "에이전트",
    "trans former",
    "transformer",
    "embedding",
    "임베딩",
)

# Build one big case-insensitive alternation regex. \b doesn't work for
# Korean (no word boundaries), so we match raw substrings instead.
_KEYWORD_RE = re.compile(
    "|".join(re.escape(k) for k in _AI_KEYWORDS),
    flags=re.IGNORECASE,
)


@dataclass(slots=True)
class RelevanceVerdict:
    is_ai: bool
    score: float  # 0..1
    matched_keywords: tuple[str, ...]
    used_llm: bool


def keyword_score(text: str) -> tuple[float, tuple[str, ...]]:
    """Score by keyword density. ``score = min(1.0, matches / 3)``."""
    if not text:
        return 0.0, ()
    matches = _KEYWORD_RE.findall(text)
    if not matches:
        return 0.0, ()
    # Preserve original-case dedup
    deduped = tuple(dict.fromkeys(m for m in matches))
    score = min(1.0, len(deduped) / 3)
    return score, deduped


def classify_with_llm(
    title: str,
    summary: str | None,
    *,
    llm: LLMClient,
) -> tuple[float, bool]:
    """Ask the LLM whether this item is AI-related.

    Returns ``(confidence, is_ai)``.
    """
    prompt = load_prompt("common/keyword-relevance-classifier.md")
    try:
        payload, _ = llm.complete_json(
            prompt.render(title=title or "(no title)", summary=(summary or "")[:600]),
            model=prompt.model,
            max_tokens=256,
        )
    except LLMError as exc:
        log.warning("relevance.llm_failed", error=str(exc))
        return 0.0, False

    is_ai = bool(payload.get("is_ai_related", False))
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return confidence, is_ai


def assess(
    title: str,
    summary: str | None,
    *,
    llm: LLMClient | None = None,
    keyword_only: bool = False,
) -> RelevanceVerdict:
    """Run keyword filter, falling back to LLM when ambiguous.

    The LLM is consulted only when the keyword score is low (0 < score < 0.34)
    and the title is non-trivial, or when ``keyword_only=False`` and the
    text is empty. ``keyword_only=True`` skips the LLM entirely.
    """
    haystack = " ".join(filter(None, (title, summary)))
    k_score, matched = keyword_score(haystack)

    if k_score >= 0.34:
        return RelevanceVerdict(is_ai=True, score=k_score, matched_keywords=matched, used_llm=False)

    if keyword_only or llm is None:
        return RelevanceVerdict(
            is_ai=k_score > 0, score=k_score, matched_keywords=matched, used_llm=False
        )

    confidence, is_ai = classify_with_llm(title, summary, llm=llm)
    # Take the max of keyword and LLM confidence as the final score.
    final = max(k_score, confidence if is_ai else 0.0)
    return RelevanceVerdict(
        is_ai=is_ai or k_score > 0,
        score=final,
        matched_keywords=matched,
        used_llm=True,
    )
