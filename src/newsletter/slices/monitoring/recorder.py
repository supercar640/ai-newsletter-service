"""Record pipeline-step + LLM-call activity into the RunLog ledger.

Design note: the recorder uses a session *separate from the caller's*.
That way a step that fails (and rolls back its own DB writes) still leaves
a ``failure`` row behind — otherwise the very rows we want to inspect post
mortem would disappear with the rollback.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from newsletter.core.db import get_sessionmaker
from newsletter.core.llm import LLMClient, LLMResponse
from newsletter.core.logging import get_logger
from newsletter.models.run_log import RunLog
from newsletter.slices.monitoring.pricing import cost_for

log = get_logger(__name__)


_ERROR_LIMIT = 500
_PERSISTED_FIELDS = (
    "step",
    "status",
    "started_at",
    "finished_at",
    "item_count",
    "llm_tokens_in",
    "llm_tokens_out",
    "cost_usd",
    "model",
    "error",
    "meta_json",
)


@contextmanager
def record_step(step: str, *, meta: dict[str, Any] | None = None) -> Iterator[RunLog]:
    """Open a RunLog row for a pipeline step.

    Yields the row so the caller can update ``item_count``, token counts,
    etc. The row is persisted twice — once on entry (``status='running'``)
    and once on exit (``success`` / ``failure``) using its own session so
    the record survives caller-side rollbacks.
    """
    sf = get_sessionmaker()

    started_at = _now()
    run = _insert_initial(sf, step=step, started_at=started_at, meta=meta)

    err: BaseException | None = None
    try:
        yield run
    except BaseException as exc:
        err = exc
        raise
    finally:
        _finalize(sf, run, error=err)


def make_llm_recorder() -> Callable[[LLMResponse], None]:
    """Return a callback that writes one RunLog row per LLM response.

    The recorder owns its session: it commits immediately and never shares
    state with the caller's transaction.
    """
    sf = get_sessionmaker()

    def record(response: LLMResponse) -> None:
        cost = cost_for(response.model, response.input_tokens, response.output_tokens)
        now = _now()
        row = RunLog(
            step="llm.complete",
            status="success",
            started_at=now,
            finished_at=now,
            llm_tokens_in=response.input_tokens,
            llm_tokens_out=response.output_tokens,
            cost_usd=cost,
            model=response.model,
        )
        session = sf()
        try:
            session.add(row)
            session.commit()
        except Exception:
            session.rollback()
            log.exception("monitoring.llm_record_failed", model=response.model)
        finally:
            session.close()

    return record


def build_llm_client(*, client: Any = None) -> LLMClient:
    """Construct an LLMClient pre-wired to record every call in RunLog."""
    return LLMClient(client=client, usage_callback=make_llm_recorder())


def _now() -> datetime:
    return datetime.now(UTC)


def _insert_initial(
    sf,
    *,
    step: str,
    started_at: datetime,
    meta: dict[str, Any] | None,
) -> RunLog:
    session = sf()
    try:
        row = RunLog(
            step=step,
            status="running",
            started_at=started_at,
            meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row
    finally:
        session.close()


def _finalize(sf, run: RunLog, *, error: BaseException | None) -> None:
    if error is not None:
        run.status = "failure"
        run.error = f"{type(error).__name__}: {error}"[:_ERROR_LIMIT]
    else:
        run.status = "success"
    run.finished_at = _now()

    session = sf()
    try:
        existing = session.get(RunLog, run.id)
        if existing is None:
            log.warning("monitoring.run_row_missing", id=run.id)
            return
        for field in _PERSISTED_FIELDS:
            setattr(existing, field, getattr(run, field))
        session.commit()
    except Exception:
        session.rollback()
        log.exception("monitoring.run_finalize_failed", step=run.step)
    finally:
        session.close()


__all__ = ["build_llm_client", "make_llm_recorder", "record_step"]
