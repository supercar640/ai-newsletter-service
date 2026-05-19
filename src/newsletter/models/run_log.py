"""RunLog (spec §10 / Iteration 10) — one row per pipeline step + per LLM call.

Two granularities share one table:

* Pipeline-step rows: ``step`` in {collect, process, integrate, draft, send,
  run} record how long each ``newsletter <step>`` invocation took, how many
  items it produced, and whether it succeeded.
* LLM-call rows: ``step="llm.complete"`` record one row per
  :class:`LLMClient.complete` call with the model and token usage.

Aggregating by ``step`` over a date gives the per-step counts/tokens/cost
table the monitoring CLI prints. Keeping LLM calls in the same table means
``stats`` can show pipeline-step durations side-by-side with their LLM cost
without a separate join.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from newsletter.core.db import Base

RUN_LOG_STATUSES: Final = ("running", "success", "failure")


def _in_clause(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class RunLog(Base):
    """One entry in the pipeline / LLM activity ledger."""

    __tablename__ = "run_logs"
    __table_args__ = (
        CheckConstraint(
            _in_clause("status", RUN_LOG_STATUSES),
            name="ck_run_logs_status",
        ),
        Index("ix_run_logs_step", "step"),
        Index("ix_run_logs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    step: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    llm_tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    llm_tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    model: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    meta_json: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"RunLog(id={self.id}, step={self.step!r}, status={self.status!r})"
