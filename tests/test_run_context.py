"""RunContext: per-run output directory."""

from __future__ import annotations

from pathlib import Path

from newsletter.core.run_context import RunContext


def test_run_context_creates_run_directory(tmp_path: Path) -> None:
    ctx = RunContext.new(tmp_path)
    assert ctx.path.exists()
    assert ctx.path.is_dir()
    assert ctx.path.parent == tmp_path / "runs"
    assert ctx.run_id


def test_run_context_subdir_creates_nested_path(tmp_path: Path) -> None:
    ctx = RunContext.new(tmp_path, run_id="r-1")
    sub = ctx.subdir("youtube", "yt-search-ai-howto")
    assert sub.exists()
    assert sub == ctx.path / "youtube" / "yt-search-ai-howto"


def test_run_context_slugifies_korean_and_spaces(tmp_path: Path) -> None:
    ctx = RunContext.new(tmp_path, run_id="r-1")
    sub = ctx.subdir("뉴 스 / 카테고리")
    # Non-ASCII gets replaced by '-' separators; result must be a real path.
    assert sub.exists()
    assert sub.is_dir()
    # No path traversal characters
    assert ".." not in sub.name
    assert "/" not in sub.name


def test_run_context_explicit_id_is_used(tmp_path: Path) -> None:
    ctx = RunContext.new(tmp_path, run_id="custom-id")
    assert ctx.run_id == "custom-id"
    assert ctx.path.name == "custom-id"
