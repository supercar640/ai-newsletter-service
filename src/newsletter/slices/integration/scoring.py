"""Importance scoring for ProcessedItem rows.

A single score combines three signals (spec §15.3 / iteration plan 4.1):

- **trust**: the source's ``trust_level`` (official > media > community)
- **recency**: exponential decay with a configurable half-life
- **LLM importance**: 1-5 enterprise-impact score, applied only to the top
  ``top_k_for_llm`` items by base score (cost guard).

The math is intentionally pure — it takes :class:`ScoreInput` dataclasses,
not ORM rows, so it can be unit-tested without a database. The integration
service is responsible for joining ProcessedItem → RawItem → Source and
materializing the inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

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


def score_items(
    items: list[ScoreInput],
    *,
    llm: _JSONCompleter | None,
    now: datetime,
    top_k_for_llm: int = 20,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> dict[int, float]:
    """Compute a final importance score per input item.

    Items not in the LLM-evaluated top-K keep their base score. The LLM
    multiplier maps importance 1..5 to a 0.5..1.5 factor (3 is neutral).
    """
    if not items:
        return {}

    base = {
        item.id: base_importance(item.trust_level, item.published_at, now, half_life_days)
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
    "ScoreInput",
    "base_importance",
    "recency_factor",
    "score_items",
]
