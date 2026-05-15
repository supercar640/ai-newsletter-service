"""Prompt loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from newsletter.core import prompts as prompts_mod
from newsletter.core.prompts import Prompt, PromptError, load_prompt


@pytest.fixture(autouse=True)
def _clear_prompt_cache() -> None:
    prompts_mod.clear_cache()


def test_loads_real_prompt() -> None:
    prompt = load_prompt("common/keyword-relevance-classifier.md")
    assert prompt.name == "keyword-relevance-classifier"
    assert prompt.model.startswith("claude-")
    assert "is_ai_related" in prompt.body
    assert "title" in prompt.inputs


def test_render_substitutes_placeholders() -> None:
    prompt = load_prompt("common/keyword-relevance-classifier.md")
    body = prompt.render(title="t", summary="s")
    assert "Title: t" in body
    assert "Summary: s" in body


def test_render_rejects_missing_inputs() -> None:
    prompt = load_prompt("common/keyword-relevance-classifier.md")
    with pytest.raises(PromptError, match="missing inputs"):
        prompt.render(title="t")


def test_malformed_prompt_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = tmp_path / "bad.md"
    bad.write_text("no frontmatter here", encoding="utf-8")
    monkeypatch.setattr(prompts_mod, "_PROMPTS_DIR", tmp_path)
    prompts_mod.clear_cache()
    with pytest.raises(PromptError):
        load_prompt("bad.md")


def test_prompt_with_only_required_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    minimal = tmp_path / "min.md"
    minimal.write_text(
        "---\nname: x\nmodel: claude-sonnet-4-6\nversion: 1\n---\nhello",
        encoding="utf-8",
    )
    monkeypatch.setattr(prompts_mod, "_PROMPTS_DIR", tmp_path)
    prompts_mod.clear_cache()
    p = load_prompt("min.md")
    assert isinstance(p, Prompt)
    assert p.body == "hello"
    assert p.inputs == ()
