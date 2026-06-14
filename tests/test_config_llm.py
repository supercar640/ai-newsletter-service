"""LLM provider selection settings."""

from __future__ import annotations

import pytest

from newsletter.core.config import Settings


def test_defaults_to_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert Settings(_env_file=None).llm_provider == "gemini"


def test_provider_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert Settings(_env_file=None).llm_provider == "anthropic"


def test_gemini_key_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "g-123")
    assert Settings(_env_file=None).gemini_api_key == "g-123"
