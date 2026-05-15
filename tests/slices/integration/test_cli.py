"""CLI integration tests for `newsletter integrate`."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from newsletter.cli import app
from newsletter.core import db as core_db
from newsletter.core.config import Settings


@pytest.fixture
def runner(settings: Settings) -> CliRunner:
    del settings  # fixture used for env-var side effects only
    core_db.reset_engine_for_tests()
    import newsletter.models  # noqa: F401 — registers models

    engine = core_db.get_engine()
    core_db.Base.metadata.create_all(engine)
    yield CliRunner()
    core_db.Base.metadata.drop_all(engine)
    core_db.reset_engine_for_tests()


def test_integrate_command_runs_on_empty_db(runner: CliRunner) -> None:
    result = runner.invoke(app, ["integrate", "--no-llm"])
    assert result.exit_code == 0, result.output
    assert "Scored: 0" in result.output


def test_integrate_help_lists_options(runner: CliRunner) -> None:
    result = runner.invoke(app, ["integrate", "--help"])
    assert result.exit_code == 0
    assert "--expert-count" in result.output
    assert "--practical-count" in result.output
    assert "--no-llm" in result.output
