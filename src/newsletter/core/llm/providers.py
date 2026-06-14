"""Provider adapters: each wraps one vendor SDK behind a uniform interface.

``LLMClient`` talks only to :class:`Provider`; it never imports a vendor SDK
or knows which one is active. An adapter's sole job is to call its SDK and
return a :class:`RawCompletion` (text + token counts).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class RawCompletion:
    text: str
    input_tokens: int
    output_tokens: int


@runtime_checkable
class Provider(Protocol):
    name: str

    def generate(
        self,
        body: str,
        *,
        model: str,
        max_tokens: int,
        system: str | None,
        temperature: float,
    ) -> RawCompletion: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, *, client: Any | None = None, api_key: str = "") -> None:
        if client is not None:
            self._client = client
        else:
            from anthropic import Anthropic

            # api_key may be empty for offline construction; the create call
            # fails loudly if the key is actually missing at call time.
            self._client = Anthropic(api_key=api_key or "missing")

    def generate(self, body, *, model, max_tokens, system, temperature) -> RawCompletion:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": body}],
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system
        response = self._client.messages.create(**kwargs)
        usage = getattr(response, "usage", None)
        return RawCompletion(
            text=_anthropic_text(response),
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        )


def _anthropic_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if not content:
        return ""
    parts = [t for block in content if (t := getattr(block, "text", None))]
    return "".join(parts)


class GeminiProvider:
    name = "gemini"

    def __init__(self, *, client: Any | None = None, api_key: str = "") -> None:
        if client is not None:
            self._client = client
        else:
            from google import genai

            self._client = genai.Client(api_key=api_key or "missing")

    def generate(self, body, *, model, max_tokens, system, temperature) -> RawCompletion:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system or None,
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        resp = self._client.models.generate_content(model=model, contents=body, config=config)
        usage = getattr(resp, "usage_metadata", None)
        return RawCompletion(
            text=getattr(resp, "text", "") or "",
            input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
            output_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
        )


def make_provider(settings) -> Provider:
    """Build the provider named by ``settings.llm_provider``."""
    name = settings.llm_provider
    if name == "anthropic":
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    if name == "gemini":
        return GeminiProvider(api_key=settings.gemini_api_key)
    raise ValueError(f"unknown LLM_PROVIDER: {name!r}")


__all__ = ["AnthropicProvider", "GeminiProvider", "Provider", "RawCompletion", "make_provider"]
