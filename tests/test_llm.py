"""LLM wrapper — response parsing, JSON extraction, error wrapping."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from newsletter.core.llm import LLMClient, LLMError, _first_json_value


@dataclass
class _FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _FakeTextBlock:
    text: str


@dataclass
class _FakeMessage:
    content: list[_FakeTextBlock]
    usage: _FakeUsage


class _FakeMessages:
    def __init__(self, message: _FakeMessage | None = None, error: Exception | None = None) -> None:
        self._message = message
        self._error = error

    def create(self, **kwargs):
        if self._error:
            raise self._error
        return self._message


class _FakeAnthropic:
    def __init__(self, message: _FakeMessage | None = None, error: Exception | None = None) -> None:
        self.messages = _FakeMessages(message=message, error=error)


def _msg(text: str, *, in_tokens: int = 5, out_tokens: int = 10) -> _FakeMessage:
    return _FakeMessage(
        content=[_FakeTextBlock(text=text)],
        usage=_FakeUsage(input_tokens=in_tokens, output_tokens=out_tokens),
    )


def test_complete_returns_text_and_usage() -> None:
    client = LLMClient(client=_FakeAnthropic(message=_msg("hello world")))
    r = client.complete("ignored")
    assert r.text == "hello world"
    assert r.input_tokens == 5
    assert r.output_tokens == 10


def test_complete_wraps_exception() -> None:
    client = LLMClient(client=_FakeAnthropic(error=RuntimeError("boom")))
    with pytest.raises(LLMError):
        client.complete("x")


def test_complete_json_handles_fenced_json() -> None:
    msg = _msg('Here you go:\n```json\n{"a": 1, "b": [2,3]}\n```')
    client = LLMClient(client=_FakeAnthropic(message=msg))
    payload, _ = client.complete_json("ignored")
    assert payload == {"a": 1, "b": [2, 3]}


def test_complete_json_handles_unfenced_json_with_prose() -> None:
    msg = _msg('Answer: {"is_ai_related": true, "confidence": 0.9}')
    client = LLMClient(client=_FakeAnthropic(message=msg))
    payload, _ = client.complete_json("ignored")
    assert payload == {"is_ai_related": True, "confidence": 0.9}


def test_complete_json_raises_when_no_json() -> None:
    msg = _msg("just prose, no JSON here")
    client = LLMClient(client=_FakeAnthropic(message=msg))
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


def test_complete_prompt_renders_and_calls() -> None:
    from pathlib import Path

    from newsletter.core.prompts import Prompt

    prompt = Prompt(
        name="t",
        model="claude-sonnet-4-6",
        version=1,
        body="Hello {name}",
        inputs=("name",),
        output_schema=None,
        path=Path("synthetic"),
    )
    captured = {}

    class _Capture(_FakeMessages):
        def create(self, **kwargs):
            captured.update(kwargs)
            return _msg("ok")

    anth = _FakeAnthropic()
    anth.messages = _Capture()
    client = LLMClient(client=anth)
    client.complete_prompt(prompt, {"name": "world"})
    assert captured["messages"] == [{"role": "user", "content": "Hello world"}]
    assert captured["model"] == "claude-sonnet-4-6"
