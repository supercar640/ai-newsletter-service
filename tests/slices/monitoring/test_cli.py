"""newsletter stats CLI."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from typer.testing import CliRunner

from newsletter.models.run_log import RunLog
from newsletter.slices.monitoring.cli import app

runner = CliRunner()


def _seed(db_session):
    d = datetime(2026, 5, 19, 9, 0, tzinfo=UTC)
    db_session.add_all(
        [
            RunLog(
                step="collect",
                status="success",
                started_at=d,
                finished_at=d + timedelta(seconds=12),
                item_count=18,
            ),
            RunLog(
                step="llm.complete",
                status="success",
                started_at=d + timedelta(seconds=20),
                finished_at=d + timedelta(seconds=21),
                llm_tokens_in=500,
                llm_tokens_out=200,
                cost_usd=0.0045,
                model="claude-sonnet-4-6",
            ),
        ]
    )
    db_session.commit()


def test_stats_command_renders_table(db_session):
    _seed(db_session)
    result = runner.invoke(app, ["--date", "2026-05-19"])
    assert result.exit_code == 0, result.stdout
    out = result.stdout
    assert "collect" in out
    assert "llm.complete" in out
    assert "18" in out  # collect item count
    # Cost formatting: $0.0045
    assert "0.00" in out


def test_stats_command_empty_when_no_rows(db_session):
    result = runner.invoke(app, ["--date", "2026-05-19"])
    assert result.exit_code == 0
    assert "(no run logs" in result.stdout


def test_stats_command_all_dates_with_no_date_flag(db_session):
    _seed(db_session)
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "collect" in result.stdout
