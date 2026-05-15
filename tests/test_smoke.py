"""Smoke tests: package and CLI wire up cleanly."""

from __future__ import annotations

from typer.testing import CliRunner

from newsletter import __version__
from newsletter.cli import app


def test_package_version_is_set() -> None:
    assert __version__ == "0.1.0"


def test_cli_help_runs() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "AI Newsletter Service" in result.output


def test_cli_version_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_cli_hello_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["hello", "--name", "master"])
    assert result.exit_code == 0
    assert "Hello, master." in result.output


def test_db_session_fixture_creates_schema(db_session) -> None:  # type: ignore[no-untyped-def]
    # If we can open and close a session, the engine + metadata round-trip works.
    assert db_session.is_active
