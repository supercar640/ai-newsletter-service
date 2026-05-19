"""Claude API price table (USD per 1M tokens).

Rates intentionally live in code rather than the DB: pricing changes are
rare, deploy-time, and require human review. ``cost_for`` is total USD
for a single call.
"""

from __future__ import annotations

# (input_per_1m, output_per_1m) in USD.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
}

# Sonnet rate as the conservative fallback — never zero so a missing key
# doesn't silently under-report cost.
_FALLBACK: tuple[float, float] = (3.0, 15.0)


# Voyage embeddings: single-rate (no output tokens).
EMBEDDING_PRICING: dict[str, float] = {
    "voyage-3-lite": 0.02,
    "voyage-3": 0.12,
    "voyage-3-large": 0.18,
}
_EMBEDDING_FALLBACK: float = 0.02


def cost_for(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = PRICING.get(model, _FALLBACK)
    return (input_tokens / 1_000_000.0) * in_rate + (output_tokens / 1_000_000.0) * out_rate


def embedding_cost_for(model: str, tokens: int) -> float:
    rate = EMBEDDING_PRICING.get(model, _EMBEDDING_FALLBACK)
    return (tokens / 1_000_000.0) * rate


__all__ = ["EMBEDDING_PRICING", "PRICING", "cost_for", "embedding_cost_for"]
