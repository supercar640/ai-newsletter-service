"""RunLog model tests (Iteration 10)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from newsletter.models.run_log import RunLog


def test_minimal_insert_defaults(db_session):
    run = RunLog(step="collect")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    assert run.id is not None
    assert run.status == "running"
    assert run.started_at is not None
    assert run.finished_at is None
    assert run.item_count == 0
    assert run.llm_tokens_in == 0
    assert run.llm_tokens_out == 0
    assert run.cost_usd == 0.0
    assert run.model is None
    assert run.error is None


def test_status_check_constraint_rejects_unknown(db_session):
    run = RunLog(step="collect", status="bogus")
    db_session.add(run)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_llm_call_row(db_session):
    run = RunLog(
        step="llm.complete",
        status="success",
        started_at=datetime(2026, 5, 19, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 5, 19, 12, 0, 1, tzinfo=UTC),
        llm_tokens_in=120,
        llm_tokens_out=45,
        cost_usd=0.0012,
        model="claude-sonnet-4-6",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    assert run.model == "claude-sonnet-4-6"
    assert run.llm_tokens_in == 120
    assert run.cost_usd == pytest.approx(0.0012)


def test_failure_carries_error_message(db_session):
    run = RunLog(
        step="process",
        status="failure",
        finished_at=datetime(2026, 5, 19, 12, 0, 1, tzinfo=UTC),
        error="RuntimeError: boom",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    assert run.status == "failure"
    assert run.error == "RuntimeError: boom"
