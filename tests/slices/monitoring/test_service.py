"""Stats aggregation service."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from newsletter.models.run_log import RunLog
from newsletter.slices.monitoring import service


@pytest.fixture
def seeded(db_session):
    d = datetime(2026, 5, 19, 9, 0, tzinfo=UTC)
    rows = [
        RunLog(
            step="collect",
            status="success",
            started_at=d,
            finished_at=d + timedelta(seconds=12),
            item_count=18,
        ),
        RunLog(
            step="process",
            status="success",
            started_at=d + timedelta(minutes=1),
            finished_at=d + timedelta(minutes=1, seconds=30),
            item_count=15,
        ),
        RunLog(
            step="llm.complete",
            status="success",
            started_at=d + timedelta(minutes=1, seconds=10),
            finished_at=d + timedelta(minutes=1, seconds=11),
            llm_tokens_in=500,
            llm_tokens_out=200,
            cost_usd=0.0045,
            model="claude-sonnet-4-6",
        ),
        RunLog(
            step="llm.complete",
            status="success",
            started_at=d + timedelta(minutes=1, seconds=20),
            finished_at=d + timedelta(minutes=1, seconds=21),
            llm_tokens_in=300,
            llm_tokens_out=100,
            cost_usd=0.0024,
            model="claude-opus-4-7",
        ),
        # Failure row to assert error count
        RunLog(
            step="integrate",
            status="failure",
            started_at=d + timedelta(minutes=2),
            finished_at=d + timedelta(minutes=2, seconds=5),
            error="RuntimeError: boom",
        ),
        # Different day; must NOT appear when filtering by 2026-05-19.
        RunLog(
            step="collect",
            status="success",
            started_at=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
            finished_at=datetime(2026, 5, 18, 9, 0, 8, tzinfo=UTC),
            item_count=5,
        ),
    ]
    db_session.add_all(rows)
    db_session.commit()
    return db_session


def test_aggregate_groups_by_step_and_filters_by_date(seeded):
    result = service.aggregate_by_step(seeded, on=date(2026, 5, 19))
    by_step = {row.step: row for row in result}
    assert set(by_step) == {"collect", "process", "integrate", "llm.complete"}
    assert by_step["collect"].run_count == 1
    assert by_step["collect"].item_count == 18
    assert by_step["llm.complete"].run_count == 2
    assert by_step["llm.complete"].llm_tokens_in == 800
    assert by_step["llm.complete"].llm_tokens_out == 300
    assert by_step["llm.complete"].cost_usd == pytest.approx(0.0069)
    assert by_step["integrate"].failure_count == 1


def test_aggregate_empty_date_returns_no_rows(seeded):
    result = service.aggregate_by_step(seeded, on=date(2026, 5, 1))
    assert result == []


def test_aggregate_all_dates_when_no_filter(seeded):
    result = service.aggregate_by_step(seeded, on=None)
    by_step = {row.step: row for row in result}
    # Both days' collects roll up together.
    assert by_step["collect"].run_count == 2
    assert by_step["collect"].item_count == 23
