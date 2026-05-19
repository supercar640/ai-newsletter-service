"""`newsletter run --until <step>` orchestrator CLI."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from newsletter.models.run_log import RunLog
from newsletter.slices.run import cli as run_cli
from newsletter.slices.run.cli import app

runner = CliRunner()


@pytest.fixture
def stub_services(monkeypatch):
    """Replace the heavy service calls with deterministic stubs."""
    calls: list[str] = []

    class _Rep:
        # CollectionReport-like / others — only the attrs the run CLI reads.
        def __init__(self):
            self.total_inserted = 3
            self.processed = 4
            self.expert_candidates = [object(), object()]
            self.practical_candidates = [object()]
            self.candidate_count = 5
            self.issue_id = 99
            self.issue_date = date(2026, 5, 19)
            self.audience = "general"

    rep = _Rep()

    def fake_collect_all(session, **kwargs):
        calls.append("collect")
        return rep

    def fake_process(session, **kwargs):
        calls.append("process")
        return rep

    def fake_integrate(session, **kwargs):
        calls.append("integrate")
        return rep

    def fake_draft_issue(session, **kwargs):
        calls.append("draft")
        return rep

    monkeypatch.setattr(run_cli, "collect_all", fake_collect_all)
    monkeypatch.setattr(run_cli, "process", fake_process)
    monkeypatch.setattr(run_cli, "integrate", fake_integrate)
    monkeypatch.setattr(run_cli, "draft_issue", fake_draft_issue)
    return calls


def _runlog_steps(db_session) -> list[str]:
    rows = list(db_session.scalars(select(RunLog).order_by(RunLog.id)).all())
    return [r.step for r in rows]


def test_run_until_collect_stops_after_collect(stub_services, db_session):
    result = runner.invoke(app, ["--until", "collect", "--date", "2026-05-19", "--no-llm"])
    assert result.exit_code == 0, result.stdout
    assert stub_services == ["collect"]
    db_session.expire_all()
    assert _runlog_steps(db_session) == ["run", "collect"]


def test_run_until_process(stub_services, db_session):
    result = runner.invoke(app, ["--until", "process", "--date", "2026-05-19", "--no-llm"])
    assert result.exit_code == 0, result.stdout
    assert stub_services == ["collect", "process"]
    db_session.expire_all()
    assert _runlog_steps(db_session) == ["run", "collect", "process"]


def test_run_until_integrate(stub_services, db_session):
    result = runner.invoke(app, ["--until", "integrate", "--date", "2026-05-19", "--no-llm"])
    assert result.exit_code == 0, result.stdout
    assert stub_services == ["collect", "process", "integrate"]
    db_session.expire_all()
    assert _runlog_steps(db_session) == ["run", "collect", "process", "integrate"]


def test_run_until_draft_skips_explicit_integrate(stub_services, db_session):
    """draft_issue calls integrate internally, so the run wrapper must
    skip the standalone integrate step to avoid double LLM work."""
    result = runner.invoke(app, ["--until", "draft", "--date", "2026-05-19", "--no-llm"])
    assert result.exit_code == 0, result.stdout
    assert stub_services == ["collect", "process", "draft"]
    db_session.expire_all()
    assert _runlog_steps(db_session) == ["run", "collect", "process", "draft"]


def test_run_rejects_invalid_until(stub_services, db_session):
    result = runner.invoke(app, ["--until", "publish", "--date", "2026-05-19"])
    assert result.exit_code != 0


def test_run_records_failure_when_step_blows_up(monkeypatch, db_session):
    def boom(session, **kwargs):
        raise RuntimeError("nope")

    monkeypatch.setattr(run_cli, "collect_all", boom)
    result = runner.invoke(app, ["--until", "collect", "--date", "2026-05-19", "--no-llm"])
    assert result.exit_code != 0
    db_session.expire_all()
    rows = list(db_session.scalars(select(RunLog).order_by(RunLog.id)).all())
    # Outer 'run' + inner 'collect' both recorded as failure
    by_step = {r.step: r for r in rows}
    assert by_step["collect"].status == "failure"
    assert by_step["run"].status == "failure"
