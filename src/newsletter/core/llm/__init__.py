"""Single chokepoint for Anthropic / Claude calls.

All slices route their LLM usage through :class:`LLMClient.complete` so
we can:

- centralize model selection (sonnet for processing, opus for final
  writing — never hardcode model strings elsewhere)
- record token usage for cost tracking
- pin the prompt body that was actually sent
- inject a fake client in tests

The client is intentionally minimal — chat history, streaming, and tool
use are not needed for current processing tasks.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic

from newsletter.core.config import get_settings
from newsletter.core.logging import get_logger
from newsletter.core.prompts import Prompt

log = get_logger(__name__)

# Model aliases (route to the current best version).
MODEL_SONNET = "claude-sonnet-4-6"
MODEL_OPUS = "claude-opus-4-7"


class LLMError(Exception):
    """Raised when an LLM call fails or returns malformed output."""


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


UsageCallback = Callable[["LLMResponse"], None]


class LLMClient:
    """Thin wrapper over the Anthropic SDK."""

    def __init__(
        self,
        *,
        client: Anthropic | None = None,
        usage_callback: UsageCallback | None = None,
    ) -> None:
        if client is not None:
            self._client = client
        else:
            settings = get_settings()
            # Anthropic SDK lets api_key be empty for offline-construction;
            # the .messages.create call will fail loudly if it's missing.
            self._client = Anthropic(api_key=settings.anthropic_api_key or "missing")
        self._usage_callback = usage_callback

    def complete(
        self,
        body: str,
        *,
        model: str = MODEL_SONNET,
        max_tokens: int = 1024,
        system: str | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Run a single-turn completion. Returns text + token usage."""
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": body}],
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        try:
            response = self._client.messages.create(**kwargs)
        except Exception as exc:
            raise LLMError(f"Anthropic call failed: {exc}") from exc

        text = _extract_text(response)
        usage = getattr(response, "usage", None)
        in_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        out_tokens = int(getattr(usage, "output_tokens", 0) or 0)

        log.info(
            "llm.complete",
            model=model,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
        )
        result = LLMResponse(
            text=text,
            model=model,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
        )
        if self._usage_callback is not None:
            try:
                self._usage_callback(result)
            except Exception:
                log.exception("llm.usage_callback_failed", model=model)
        return result

    def complete_prompt(
        self,
        prompt: Prompt,
        values: dict[str, Any],
        *,
        max_tokens: int = 1024,
        system: str | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Render a :class:`Prompt` with ``values`` and call ``complete``."""
        body = prompt.render(**values)
        return self.complete(
            body,
            model=prompt.model,
            max_tokens=max_tokens,
            system=system,
            temperature=temperature,
        )

    def complete_json(
        self,
        body: str,
        *,
        model: str = MODEL_SONNET,
        max_tokens: int = 1024,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> tuple[Any, LLMResponse]:
        """Run a completion and parse the response as JSON.

        Pulls the first balanced JSON object out of the response so the
        model can wrap output in ```json fences or prose without breaking us.
        """
        response = self.complete(
            body,
            model=model,
            max_tokens=max_tokens,
            system=system,
            temperature=temperature,
        )
        payload = _first_json_value(response.text)
        if payload is None:
            raise LLMError(f"LLM did not return parseable JSON. Raw: {response.text[:200]!r}")
        return payload, response


def _extract_text(response: Any) -> str:
    """Pull the text part out of an Anthropic Message response."""
    content = getattr(response, "content", None)
    if not content:
        return ""
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


def _first_json_value(text: str) -> Any:
    """Find and parse the first JSON object/array in ``text``.

    Handles fenced blocks (```json ... ```), leading/trailing prose, and
    multi-line objects. Returns ``None`` if no parseable value is found.
    """
    if not text:
        return None

    # Strip fenced ```json blocks if present.
    fenced_start = text.find("```")
    if fenced_start != -1:
        rest = text[fenced_start + 3 :]
        # skip the optional language tag (e.g. ```json\n)
        nl = rest.find("\n")
        if nl != -1:
            rest = rest[nl + 1 :]
        fenced_end = rest.find("```")
        if fenced_end != -1:
            candidate = rest[:fenced_end].strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass  # fall through to brace scan

    # Find a balanced { ... } or [ ... ] span.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
    return None
