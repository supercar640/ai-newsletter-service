"""Provider-agnostic LLM client.

All slices route their LLM usage through :class:`LLMClient.complete` so we
can centralize tier→model resolution, record token usage for cost tracking,
and inject a fake provider in tests. The client talks only to a
:class:`Provider` — it never imports a vendor SDK or knows which one is active.

A *tier* (``FAST`` / ``QUALITY``) names the role the call plays; the active
provider plus the tier resolve to the concrete model id at call time.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from newsletter.core.config import get_settings
from newsletter.core.llm.models import FAST, resolve_model
from newsletter.core.llm.providers import Provider, make_provider
from newsletter.core.logging import get_logger
from newsletter.core.prompts import Prompt

log = get_logger(__name__)


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
    """Provider-agnostic wrapper. Picks a model by tier + active provider."""

    def __init__(
        self,
        *,
        provider: Provider | None = None,
        usage_callback: UsageCallback | None = None,
    ) -> None:
        self._provider = provider if provider is not None else make_provider(get_settings())
        self._usage_callback = usage_callback

    def complete(
        self,
        body: str,
        *,
        tier: str = FAST,
        max_tokens: int = 1024,
        system: str | None = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Run a single-turn completion. Returns text + token usage.

        The concrete model id (resolved from provider + tier) is recorded on
        the response so cost tracking reflects what was actually called.
        """
        model = resolve_model(self._provider.name, tier)
        try:
            raw = self._provider.generate(
                body,
                model=model,
                max_tokens=max_tokens,
                system=system,
                temperature=temperature,
            )
        except Exception as exc:
            raise LLMError(f"{self._provider.name} call failed: {exc}") from exc

        log.info(
            "llm.complete",
            model=model,
            input_tokens=raw.input_tokens,
            output_tokens=raw.output_tokens,
        )
        result = LLMResponse(
            text=raw.text,
            model=model,
            input_tokens=raw.input_tokens,
            output_tokens=raw.output_tokens,
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
        return self.complete(
            prompt.render(**values),
            tier=prompt.tier,
            max_tokens=max_tokens,
            system=system,
            temperature=temperature,
        )

    def complete_json(
        self,
        body: str,
        *,
        tier: str = FAST,
        max_tokens: int = 1024,
        system: str | None = None,
        temperature: float = 0.0,
    ) -> tuple[Any, LLMResponse]:
        """Run a completion and parse the first balanced JSON value out of it."""
        response = self.complete(
            body,
            tier=tier,
            max_tokens=max_tokens,
            system=system,
            temperature=temperature,
        )
        payload = _first_json_value(response.text)
        if payload is None:
            raise LLMError(f"LLM did not return parseable JSON. Raw: {response.text[:200]!r}")
        return payload, response


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


__all__ = ["LLMClient", "LLMError", "LLMResponse", "_first_json_value"]
