"""LLMClient — tier→model resolution, JSON extraction, error wrapping, usage."""

from __future__ import annotations

from pathlib import Path

import pytest

from newsletter.core.llm import LLMClient, LLMError, _first_json_value
from newsletter.core.llm.providers import RawCompletion


class FakeProvider:
    """Minimal provider double. Records the model id it was asked for."""

    def __init__(
        self, *, text: str = "", error: Exception | None = None, name: str = "anthropic"
    ) -> None:
        self.name = name
        self._text = text
        self._error = error
        self.captured: dict = {}

    def generate(self, body, *, model, max_tokens, system, temperature) -> RawCompletion:
        self.captured = {
            "body": body,
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "temperature": temperature,
        }
        if self._error:
            raise self._error
        return RawCompletion(text=self._text, input_tokens=5, output_tokens=10)


def test_complete_returns_text_and_usage() -> None:
    client = LLMClient(provider=FakeProvider(text="hello world"))
    r = client.complete("ignored")
    assert r.text == "hello world"
    assert r.input_tokens == 5
    assert r.output_tokens == 10


def test_complete_resolves_tier_to_concrete_model() -> None:
    provider = FakeProvider(text="x", name="anthropic")
    r = LLMClient(provider=provider).complete("body", tier="quality")
    assert provider.captured["model"] == "claude-opus-4-7"
    assert r.model == "claude-opus-4-7"


def test_complete_wraps_exception() -> None:
    client = LLMClient(provider=FakeProvider(error=RuntimeError("boom")))
    with pytest.raises(LLMError):
        client.complete("x")


def test_complete_json_handles_fenced_json() -> None:
    client = LLMClient(
        provider=FakeProvider(text='Here you go:\n```json\n{"a": 1, "b": [2,3]}\n```')
    )
    payload, _ = client.complete_json("ignored")
    assert payload == {"a": 1, "b": [2, 3]}


def test_complete_json_handles_unfenced_json_with_prose() -> None:
    client = LLMClient(
        provider=FakeProvider(text='Answer: {"is_ai_related": true, "confidence": 0.9}')
    )
    payload, _ = client.complete_json("ignored")
    assert payload == {"is_ai_related": True, "confidence": 0.9}


def test_complete_json_raises_when_no_json() -> None:
    client = LLMClient(provider=FakeProvider(text="just prose, no JSON here"))
    with pytest.raises(LLMError, match="parseable JSON"):
        client.complete_json("x")


def test_first_json_value_array() -> None:
    assert _first_json_value("see [1, 2, 3] please") == [1, 2, 3]


def test_first_json_value_nested_braces_in_string() -> None:
    text = '{"name": "value with } brace", "x": 1}'
    assert _first_json_value(text) == {"name": "value with } brace", "x": 1}


def test_first_json_value_returns_none_on_empty() -> None:
    assert _first_json_value("") is None
    assert _first_json_value("plain text") is None


def test_complete_prompt_renders_and_uses_prompt_tier() -> None:
    from newsletter.core.prompts import Prompt

    prompt = Prompt(
        name="t",
        tier="fast",
        version=1,
        body="Hello {name}",
        inputs=("name",),
        output_schema=None,
        path=Path("synthetic"),
    )
    provider = FakeProvider(text="ok")
    LLMClient(provider=provider).complete_prompt(prompt, {"name": "world"})
    assert provider.captured["body"] == "Hello world"
    # fast tier + anthropic provider → sonnet
    assert provider.captured["model"] == "claude-sonnet-4-6"
