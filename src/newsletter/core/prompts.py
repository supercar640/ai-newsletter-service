"""Prompt loader for ``prompts/`` directory.

Every prompt file is markdown with a YAML frontmatter block. The body
below the second ``---`` is the literal text rendered to the model.

```
---
name: expert-importance-scorer
model: claude-sonnet-4-6
version: 1
inputs: [title, summary, source_name]
output_schema: {"importance": "int 1-5", "rationale": "string"}
---

You are scoring AI-news importance for an enterprise audience...
```
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


class PromptError(Exception):
    """Raised when a prompt file is missing or malformed."""


@dataclass(slots=True, frozen=True)
class Prompt:
    name: str
    model: str
    version: int
    body: str
    inputs: tuple[str, ...]
    output_schema: Any
    path: Path

    def render(self, **values: Any) -> str:
        """Substitute ``{name}`` placeholders in the body with ``values``."""
        missing = [k for k in self.inputs if k not in values]
        if missing:
            raise PromptError(f"prompt {self.name!r} missing inputs: {sorted(missing)}")
        try:
            return self.body.format(**values)
        except KeyError as exc:
            raise PromptError(
                f"prompt {self.name!r} references undeclared placeholder {exc}"
            ) from exc


def prompts_dir() -> Path:
    """Return the root prompts directory (overridable for tests)."""
    return _PROMPTS_DIR


@lru_cache(maxsize=64)
def load_prompt(rel_path: str) -> Prompt:
    """Load and parse a prompt file under ``prompts/``.

    The argument is a path relative to the prompts directory,
    e.g. ``"expert-news/expert-importance-scorer.md"``.
    """
    full = prompts_dir() / rel_path
    if not full.is_file():
        raise PromptError(f"prompt file not found: {full}")
    text = full.read_text(encoding="utf-8")
    return _parse_prompt(text, path=full)


def clear_cache() -> None:
    """Reset the in-memory prompt cache (used by tests)."""
    load_prompt.cache_clear()


def _parse_prompt(text: str, *, path: Path) -> Prompt:
    if not text.startswith("---"):
        raise PromptError(f"{path.name}: must start with YAML frontmatter (---)")
    rest = text[3:].lstrip("\n")
    end = rest.find("\n---")
    if end == -1:
        raise PromptError(f"{path.name}: missing closing '---' for frontmatter")

    frontmatter = rest[:end]
    body = rest[end + len("\n---") :].lstrip("\n").rstrip()

    try:
        meta = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError as exc:
        raise PromptError(f"{path.name}: invalid YAML frontmatter: {exc}") from exc

    if not isinstance(meta, dict):
        raise PromptError(f"{path.name}: frontmatter must be a mapping")

    required = ("name", "model", "version")
    missing = [k for k in required if k not in meta]
    if missing:
        raise PromptError(f"{path.name}: frontmatter missing keys: {missing}")

    inputs_raw = meta.get("inputs") or []
    if not isinstance(inputs_raw, list):
        raise PromptError(f"{path.name}: 'inputs' must be a list")

    return Prompt(
        name=str(meta["name"]),
        model=str(meta["model"]),
        version=int(meta["version"]),
        body=body,
        inputs=tuple(str(x) for x in inputs_raw),
        output_schema=meta.get("output_schema"),
        path=path,
    )
