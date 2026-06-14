"""tier → concrete model-id resolution per provider."""

from __future__ import annotations

import pytest

from newsletter.core.llm.models import FAST, MODELS, QUALITY, resolve_model


def test_resolve_anthropic() -> None:
    assert resolve_model("anthropic", FAST) == "claude-sonnet-4-6"
    assert resolve_model("anthropic", QUALITY) == "claude-opus-4-7"


def test_resolve_gemini() -> None:
    assert resolve_model("gemini", FAST) == "gemini-2.5-flash"
    # Free tier: quality maps to flash until Tier 1 billing unlocks 2.5-pro.
    assert resolve_model("gemini", QUALITY) == "gemini-2.5-flash"


def test_every_provider_defines_both_tiers() -> None:
    for provider, tiers in MODELS.items():
        assert set(tiers) == {FAST, QUALITY}, provider


def test_resolve_unknown_provider_raises() -> None:
    with pytest.raises(KeyError):
        resolve_model("nope", FAST)


def test_resolve_unknown_tier_raises() -> None:
    with pytest.raises(KeyError):
        resolve_model("anthropic", "turbo")
