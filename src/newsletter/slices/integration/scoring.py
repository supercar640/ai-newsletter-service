"""Importance scoring for ProcessedItem rows.

A single score combines four signals (spec §15.3 + Phase 2):

- **trust**: the source's ``trust_level`` (official > media > community)
- **recency**: exponential decay with a configurable half-life
- **LLM importance**: 1-5 enterprise-impact score, applied only to the top
  ``top_k_for_llm`` items by base score (cost guard).
- **company interest**: keyword + embedding match against operator-curated
  topics. Multiplier in [1.0, 1.5] — never *de-boosts*, only raises items
  that touch focus areas the company wants over-weighted.

The math is intentionally pure — it takes :class:`ScoreInput` dataclasses,
not ORM rows, so it can be unit-tested without a database. The integration
service is responsible for joining ProcessedItem → RawItem → Source and
materializing the inputs.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from newsletter.core.embeddings import cosine
from newsletter.core.llm import LLMError
from newsletter.core.logging import get_logger
from newsletter.core.prompts import load_prompt

log = get_logger(__name__)


TRUST_WEIGHTS: Final[dict[str, float]] = {
    "official": 1.0,
    "media": 0.7,
    "community": 0.4,
}
"""Mapping from ``Source.trust_level`` to a base weight in (0, 1]."""

_DEFAULT_TRUST_WEIGHT: Final[float] = 0.5
_DEFAULT_HALF_LIFE_DAYS: Final[float] = 3.0


@dataclass(slots=True, frozen=True)
class ScoreInput:
    """Pure-data view of a ProcessedItem for scoring purposes."""

    id: int
    trust_level: str
    published_at: datetime | None
    title: str
    summary: str | None
    source_name: str


@dataclass(slots=True, frozen=True)
class InterestProfile:
    """One company-interest entry materialized for scoring.

    ``keywords`` is stored lowercased so callers can match against
    pre-lowercased item text without redundant transforms.
    """

    id: int
    name: str
    keywords: tuple[str, ...]
    weight: float
    embedding: Sequence[float] | None


@dataclass(slots=True, frozen=True)
class CorpusChunk:
    """One company-document chunk materialized for relevance scoring.

    ``keywords`` is lowercased so callers match against pre-lowercased text.
    """

    keywords: tuple[str, ...]
    embedding: Sequence[float] | None


# Interest matching tuning knobs.
_INTEREST_CAP: Final[float] = 0.5
_INTEREST_PER_HIT_STRENGTH: Final[float] = 0.1
_INTEREST_COSINE_THRESHOLD: Final[float] = 0.55

# Corpus (company-document) relevance tuning. Capped lower than interests
# because both boosts compound on the base score.
_CORPUS_CAP: Final[float] = 0.3
_CORPUS_COSINE_THRESHOLD: Final[float] = 0.55
_CORPUS_KEYWORD_SATURATION: Final[int] = 3


class _JSONCompleter(Protocol):
    """Subset of :class:`LLMClient` that the scorer actually needs."""

    def complete_json(
        self,
        body: str,
        *,
        model: str = ...,
        max_tokens: int = ...,
        system: str | None = ...,
        temperature: float = ...,
    ): ...


def recency_factor(
    published_at: datetime | None,
    now: datetime,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> float:
    """Return an exponential-decay factor in (0, 1].

    Missing ``published_at`` is treated as a neutral 0.5 rather than 0 —
    we don't want to punish items that lack a parseable date entirely.
    Future timestamps (clock skew from feeds) clamp to 1.0.
    """
    if published_at is None:
        return 0.5
    age = (now - published_at).total_seconds() / 86400.0
    if age <= 0.0:
        return 1.0
    return math.exp(-math.log(2.0) * age / half_life_days)


def base_importance(
    trust_level: str,
    published_at: datetime | None,
    now: datetime,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> float:
    """Return ``trust * recency`` in (0, 1]."""
    weight = TRUST_WEIGHTS.get(trust_level, _DEFAULT_TRUST_WEIGHT)
    return weight * recency_factor(published_at, now, half_life_days)


def interest_match_factor(
    *,
    title: str,
    summary: str | None,
    item_embedding: Sequence[float] | None,
    interests: list[InterestProfile],
) -> float:
    """Return a multiplier in [1.0, 1.5] from company-interest signals.

    Two paths per interest:

    * **Keyword** — any of ``interest.keywords`` (already lowercased) appears
      in ``title + summary`` (lowercased once here).
    * **Embedding cosine** — when both sides have a vector, similarity above
      :data:`_INTEREST_COSINE_THRESHOLD` contributes a linearly-scaled signal.

    The stronger of the two signals per interest is multiplied by the
    interest's ``weight``, scaled by ``per_hit_strength``, summed across all
    interests, and clamped to ``cap``. ``cap`` of 0.5 means a 50% top-end
    boost relative to the unscored item.
    """
    if not interests:
        return 1.0
    text = (title + " " + (summary or "")).lower()
    total = 0.0
    for interest in interests:
        keyword_strength = 1.0 if _has_any_keyword(text, interest.keywords) else 0.0
        cosine_strength = 0.0
        if item_embedding is not None and interest.embedding is not None:
            c = cosine(item_embedding, interest.embedding)
            if c >= _INTEREST_COSINE_THRESHOLD:
                cosine_strength = (c - _INTEREST_COSINE_THRESHOLD) / (
                    1.0 - _INTEREST_COSINE_THRESHOLD
                )
        signal = max(keyword_strength, cosine_strength)
        total += signal * interest.weight * _INTEREST_PER_HIT_STRENGTH
    return 1.0 + min(_INTEREST_CAP, total)


def _has_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(kw in text for kw in keywords if kw)


def corpus_relevance_factor(
    *,
    title: str,
    summary: str | None,
    item_embedding: Sequence[float] | None,
    chunks: list[CorpusChunk],
) -> float:
    """Return a multiplier in [1.0, 1.0 + _CORPUS_CAP] from corpus relevance.

    Prefers the embedding path (max cosine over embedded chunks). When the
    item has no embedding or no chunk is embedded, falls back to counting
    distinct corpus keywords present in the item text.
    """
    if not chunks:
        return 1.0

    embedded = [c.embedding for c in chunks if c.embedding is not None]
    if item_embedding is not None and embedded:
        best = max(cosine(item_embedding, vec) for vec in embedded)
        if best < _CORPUS_COSINE_THRESHOLD:
            return 1.0
        strength = (best - _CORPUS_COSINE_THRESHOLD) / (
            1.0 - _CORPUS_COSINE_THRESHOLD
        )
    else:
        text = (title + " " + (summary or "")).lower()
        keywords = {kw for chunk in chunks for kw in chunk.keywords if kw}
        hits = sum(1 for kw in keywords if kw in text)
        if hits == 0:
            return 1.0
        strength = min(1.0, hits / _CORPUS_KEYWORD_SATURATION)

    return 1.0 + strength * _CORPUS_CAP


def score_items(
    items: list[ScoreInput],
    *,
    llm: _JSONCompleter | None,
    now: datetime,
    top_k_for_llm: int = 20,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
    interests: list[InterestProfile] | None = None,
    item_embeddings: dict[int, Sequence[float]] | None = None,
    corpus_chunks: list[CorpusChunk] | None = None,
) -> dict[int, float]:
    """Compute a final importance score per input item.

    Items not in the LLM-evaluated top-K keep their base score. The LLM
    multiplier maps importance 1..5 to a 0.5..1.5 factor (3 is neutral).
    The interest multiplier (when ``interests`` is non-empty) compounds on
    top, expressed as a 1.0..1.5 factor.
    """
    if not items:
        return {}

    embeddings_by_id = item_embeddings or {}
    interest_list = interests or []
    corpus_list = corpus_chunks or []

    base = {
        item.id: base_importance(item.trust_level, item.published_at, now, half_life_days)
        * interest_match_factor(
            title=item.title,
            summary=item.summary,
            item_embedding=embeddings_by_id.get(item.id),
            interests=interest_list,
        )
        * corpus_relevance_factor(
            title=item.title,
            summary=item.summary,
            item_embedding=embeddings_by_id.get(item.id),
            chunks=corpus_list,
        )
        for item in items
    }
    if llm is None or top_k_for_llm <= 0:
        return base

    by_id = {item.id: item for item in items}
    top_ids = sorted(base, key=lambda i: base[i], reverse=True)[:top_k_for_llm]

    final = dict(base)
    for item_id in top_ids:
        importance = _llm_importance(by_id[item_id], llm=llm)
        if importance is None:
            continue
        multiplier = _multiplier_for(importance)
        final[item_id] = base[item_id] * multiplier
    return final


def _multiplier_for(importance: int) -> float:
    """Map 1..5 → 0.5..1.5 (3 is neutral)."""
    clamped = max(1, min(5, importance))
    return 0.5 + (clamped - 1) * 0.25


def _llm_importance(item: ScoreInput, *, llm: _JSONCompleter) -> int | None:
    """Ask the LLM for a 1..5 importance score. Returns ``None`` on error."""
    try:
        prompt = load_prompt("expert-news/expert-importance-scorer.md")
        body = prompt.render(
            title=item.title or "(no title)",
            summary=(item.summary or "")[:600],
            source_name=item.source_name or "(unknown)",
        )
        payload, _ = llm.complete_json(body, model=prompt.model, max_tokens=128)
    except LLMError as exc:
        log.warning("scoring.llm_failed", item_id=item.id, error=str(exc))
        return None
    except Exception as exc:
        log.warning("scoring.llm_error", item_id=item.id, error=str(exc))
        return None

    raw = payload.get("importance") if isinstance(payload, dict) else None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        log.warning("scoring.llm_bad_payload", item_id=item.id, raw=raw)
        return None
    return value


__all__ = [
    "TRUST_WEIGHTS",
    "CorpusChunk",
    "InterestProfile",
    "ScoreInput",
    "base_importance",
    "corpus_relevance_factor",
    "interest_match_factor",
    "recency_factor",
    "score_items",
]
