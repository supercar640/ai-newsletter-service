"""CLI integration tests for `newsletter sources ...`.

These run the Typer app end-to-end against an in-memory DB. They rely on
the ``settings`` fixture from conftest to point ``DB_URL`` at memory.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from newsletter.cli import app
from newsletter.core import db as core_db
from newsletter.core.config import Settings


@pytest.fixture
def runner(settings: Settings) -> CliRunner:
    """Reset DB and prepare schema so CLI commands have a usable DB.

    The ``settings`` fixture is requested for its env-var side effects
    (sets ``DB_URL`` to in-memory SQLite) even though it is not used directly.
    """
    del settings  # silence unused-arg readers — fixture is depended on for side effects
    core_db.reset_engine_for_tests()
    import newsletter.models  # noqa: F401 — registers models

    engine = core_db.get_engine()
    core_db.Base.metadata.create_all(engine)
    yield CliRunner()
    core_db.Base.metadata.drop_all(engine)
    core_db.reset_engine_for_tests()


def test_sources_list_empty(runner: CliRunner) -> None:
    result = runner.invoke(app, ["sources", "list"])
    assert result.exit_code == 0
    assert "(no sources)" in result.output


def test_sources_seed_then_list(runner: CliRunner) -> None:
    seed_result = runner.invoke(app, ["sources", "seed"])
    assert seed_result.exit_code == 0
    assert "Seed complete:" in seed_result.output

    list_result = runner.invoke(app, ["sources", "list"])
    assert list_result.exit_code == 0
    assert "naver-ai" in list_result.output
    assert "openai-blog" in list_result.output


def test_sources_seed_is_idempotent(runner: CliRunner) -> None:
    first = runner.invoke(app, ["sources", "seed"])
    second = runner.invoke(app, ["sources", "seed"])
    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "0 created" in second.output


def test_sources_add_and_show(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        [
            "sources",
            "add",
            "--id",
            "custom-rss",
            "--name",
            "Custom RSS",
            "--type",
            "RSS",
            "--track",
            "expert_news",
            "--endpoint",
            "https://example.com/feed.xml",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Added source: custom-rss" in result.output

    show = runner.invoke(app, ["sources", "show", "custom-rss"])
    assert show.exit_code == 0
    payload = json.loads(show.output)
    assert payload["source_id"] == "custom-rss"
    assert payload["type"] == "RSS"


def test_sources_add_rejects_invalid_id(runner: CliRunner) -> None:
    result = runner.invoke(
        app,
        [
            "sources",
            "add",
            "--id",
            "BAD ID",
            "--name",
            "X",
            "--type",
            "RSS",
            "--track",
            "expert_news",
            "--endpoint",
            "https://example.com",
        ],
    )
    assert result.exit_code == 2
    assert "Invalid input" in result.output


def test_sources_disable_missing_fails(runner: CliRunner) -> None:
    result = runner.invoke(app, ["sources", "disable", "ghost"])
    assert result.exit_code == 1
    assert "Source not found" in result.output


def test_sources_disable_then_list_filtered(runner: CliRunner) -> None:
    runner.invoke(app, ["sources", "seed"])
    runner.invoke(app, ["sources", "disable", "naver-ai"])

    only_enabled = runner.invoke(app, ["sources", "list", "--enabled"])
    assert only_enabled.exit_code == 0
    assert "naver-ai" not in only_enabled.output
    assert "techcrunch-ai" in only_enabled.output


def test_sources_list_json(runner: CliRunner) -> None:
    runner.invoke(app, ["sources", "seed"])
    result = runner.invoke(app, ["sources", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    ids = {row["source_id"] for row in data}
    assert "naver-ai" in ids
