"""Tier → concrete model-id resolution, per provider.

A *tier* names the role a prompt plays (``fast`` for per-item processing,
``quality`` for final writing/editing) without committing to a vendor.
The active provider plus the tier resolve to the concrete model id at call
time, so prompts and slices stay provider-agnostic.
"""

from __future__ import annotations

FAST = "fast"
QUALITY = "quality"

MODELS: dict[str, dict[str, str]] = {
    "anthropic": {FAST: "claude-sonnet-4-6", QUALITY: "claude-opus-4-7"},
    # Free tier blocks 2.5-pro (quota limit 0); quality falls back to flash.
    # Restore QUALITY to "gemini-2.5-pro" once billing (Tier 1) is enabled.
    "gemini": {FAST: "gemini-2.5-flash", QUALITY: "gemini-2.5-flash"},
}


def resolve_model(provider: str, tier: str) -> str:
    """Map ``(provider, tier)`` to the concrete model id.

    Raises ``KeyError`` if the provider or tier is unknown — a loud failure
    beats silently picking a default model.
    """
    return MODELS[provider][tier]


__all__ = ["FAST", "MODELS", "QUALITY", "resolve_model"]
