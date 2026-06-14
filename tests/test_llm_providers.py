"""Provider adapters — request shaping + token extraction per vendor SDK."""

from __future__ import annotations

from dataclasses import dataclass

from newsletter.core.llm.providers import AnthropicProvider, RawCompletion


@dataclass
class _Usage:
    input_tokens: int
    output_tokens: int


@dataclass
class _Block:
    text: str


@dataclass
class _Msg:
    content: list
    usage: _Usage


class _Messages:
    def __init__(self) -> None:
        self.captured: dict = {}

    def create(self, **kw):
        self.captured = kw
        return _Msg(content=[_Block("hi")], usage=_Usage(3, 7))


class _Anthropic:
    def __init__(self) -> None:
        self.messages = _Messages()


def test_anthropic_generate_extracts_text_and_tokens() -> None:
    sdk = _Anthropic()
    provider = AnthropicProvider(client=sdk)
    out = provider.generate(
        "body", model="claude-sonnet-4-6", max_tokens=100, system="sys", temperature=0.2
    )
    assert isinstance(out, RawCompletion)
    assert out.text == "hi"
    assert (out.input_tokens, out.output_tokens) == (3, 7)
    assert sdk.messages.captured["model"] == "claude-sonnet-4-6"
    assert sdk.messages.captured["system"] == "sys"
    assert sdk.messages.captured["messages"] == [{"role": "user", "content": "body"}]
    assert sdk.messages.captured["temperature"] == 0.2


def test_anthropic_omits_system_when_none() -> None:
    sdk = _Anthropic()
    AnthropicProvider(client=sdk).generate(
        "body", model="m", max_tokens=10, system=None, temperature=0.0
    )
    assert "system" not in sdk.messages.captured


def test_anthropic_name() -> None:
    assert AnthropicProvider(client=_Anthropic()).name == "anthropic"
