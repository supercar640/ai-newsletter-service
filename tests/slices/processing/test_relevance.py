"""Relevance assessment — keyword + LLM."""

from __future__ import annotations

from dataclasses import dataclass

from newsletter.core.llm import LLMResponse
from newsletter.slices.processing import relevance


def test_keyword_score_matches() -> None:
    score, matched = relevance.keyword_score("OpenAI announces GPT-5 model update")
    assert score > 0
    assert any("GPT" in m or "OpenAI" in m for m in matched)


def test_keyword_score_no_match() -> None:
    score, matched = relevance.keyword_score("Tesla quarterly earnings beat forecast")
    assert score == 0.0
    assert matched == ()


def test_keyword_score_korean() -> None:
    score, matched = relevance.keyword_score("생성형 AI 도구가 업무를 바꾼다")
    assert score > 0
    assert any(m in {"AI", "생성형"} for m in matched)


def test_assess_high_keyword_score_skips_llm() -> None:
    class _NoCallLLM:
        def complete_json(self, *a, **kw):
            raise AssertionError("LLM should not be consulted")

    verdict = relevance.assess(
        "OpenAI Anthropic Google launch new LLMs",
        "About GPT, Claude, and Gemini",
        llm=_NoCallLLM(),  # type: ignore[arg-type]
    )
    assert verdict.is_ai is True
    assert verdict.used_llm is False
    assert verdict.score >= 0.34


def test_assess_keyword_only_skips_llm() -> None:
    @dataclass
    class _ShouldNotCall:
        called: bool = False

        def complete_json(self, *a, **kw):
            self.called = True

    fake = _ShouldNotCall()
    verdict = relevance.assess(
        "Some ambiguous topic",
        "Brief text",
        llm=fake,
        keyword_only=True,  # type: ignore[arg-type]
    )
    assert fake.called is False
    assert verdict.used_llm is False


def test_assess_low_keyword_triggers_llm_positive() -> None:
    class _PositiveLLM:
        def complete_json(self, *a, **kw):
            return {"is_ai_related": True, "confidence": 0.9}, LLMResponse(
                "x", "claude-sonnet-4-6", 5, 5
            )

    verdict = relevance.assess(
        "Quiet headline mentioning a chatbot launch",
        None,
        llm=_PositiveLLM(),  # type: ignore[arg-type]
    )
    assert verdict.is_ai is True
    assert verdict.used_llm is True
    assert verdict.score >= 0.9


def test_assess_low_keyword_llm_says_no() -> None:
    class _NegativeLLM:
        def complete_json(self, *a, **kw):
            return {"is_ai_related": False, "confidence": 0.8}, LLMResponse(
                "x", "claude-sonnet-4-6", 5, 5
            )

    verdict = relevance.assess(
        "Tesla earnings report",
        "Quarterly miss",
        llm=_NegativeLLM(),  # type: ignore[arg-type]
    )
    assert verdict.is_ai is False
    assert verdict.used_llm is True
    assert verdict.score == 0.0


def test_assess_llm_failure_returns_keyword_only() -> None:
    class _BrokenLLM:
        def complete_json(self, *a, **kw):
            from newsletter.core.llm import LLMError

            raise LLMError("network")

    verdict = relevance.assess(
        "Quiet headline mentioning a chatbot",
        None,
        llm=_BrokenLLM(),  # type: ignore[arg-type]
    )
    # No keyword hit AND LLM failed → not AI.
    assert verdict.is_ai is False
