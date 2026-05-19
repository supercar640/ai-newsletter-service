"""Aggregate the RunLog ledger into per-step stats for the CLI table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.models.run_log import RunLog


@dataclass(slots=True, frozen=True)
class StepStats:
    step: str
    run_count: int
    success_count: int
    failure_count: int
    item_count: int
    llm_tokens_in: int
    llm_tokens_out: int
    cost_usd: float


def aggregate_by_step(session: Session, *, on: date | None) -> list[StepStats]:
    """Return one :class:`StepStats` per ``step`` for rows on ``on`` (or all dates).

    Output is sorted by step for stable CLI rendering.
    """
    stmt = select(RunLog)
    if on is not None:
        start = datetime.combine(on, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)
        stmt = stmt.where(RunLog.started_at >= start, RunLog.started_at < end)

    rows = list(session.scalars(stmt).all())
    if not rows:
        return []

    buckets: dict[str, list[RunLog]] = {}
    for row in rows:
        buckets.setdefault(row.step, []).append(row)

    out: list[StepStats] = []
    for step in sorted(buckets):
        group = buckets[step]
        out.append(
            StepStats(
                step=step,
                run_count=len(group),
                success_count=sum(1 for r in group if r.status == "success"),
                failure_count=sum(1 for r in group if r.status == "failure"),
                item_count=sum(r.item_count for r in group),
                llm_tokens_in=sum(r.llm_tokens_in for r in group),
                llm_tokens_out=sum(r.llm_tokens_out for r in group),
                cost_usd=sum(r.cost_usd for r in group),
            )
        )
    return out


__all__ = ["StepStats", "aggregate_by_step"]
