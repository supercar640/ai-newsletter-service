"""Track classification."""

from __future__ import annotations

import pytest

from newsletter.core.llm import LLMResponse
from newsletter.models.source import Source
from newsletter.slices.processing.track_classifier import classify


def _make_source(track: str) -> Source:
    return Source(
        source_id="t",
        name="t",
        type="RSS",
        content_track=track,
        endpoint="https://example.com",
        priority="medium",
        trust_level="media",
        enabled=True,
        fetch_interval="daily",
        auth_required=False,
    )


@pytest.mark.parametrize("track", ["expert_news", "practical_insight"])
def test_fixed_track_short_circuits(track: str) -> None:
    src = _make_source(track)
    assert classify(src, "anything", "summary") == track


def test_both_track_no_llm_defaults_expert() -> None:
    src = _make_source("both")
    assert classify(src, "anything", "summary", llm=None) == "expert_news"


def test_both_track_llm_returns_practical() -> None:
    class _LLM:
        def complete_json(self, *a, **kw):
            return {"track": "practical_insight"}, LLMResponse("x", "m", 1, 1)

    src = _make_source("both")
    result = classify(src, "5 ways to use ChatGPT", "tutorial", llm=_LLM())  # type: ignore[arg-type]
    assert result == "practical_insight"


def test_both_track_llm_invalid_value_falls_back() -> None:
    class _LLM:
        def complete_json(self, *a, **kw):
            return {"track": "bogus"}, LLMResponse("x", "m", 1, 1)

    src = _make_source("both")
    result = classify(src, "x", "y", llm=_LLM())  # type: ignore[arg-type]
    assert result == "expert_news"


def test_both_track_llm_error_falls_back() -> None:
    class _LLM:
        def complete_json(self, *a, **kw):
            from newsletter.core.llm import LLMError

            raise LLMError("boom")

    src = _make_source("both")
    result = classify(src, "x", "y", llm=_LLM())  # type: ignore[arg-type]
    assert result == "expert_news"
