"""`newsletter run --until <step>` — orchestrate the pipeline end-to-end.

Stops after the step named by ``--until``. Each step records its own
``RunLog`` row, and the outer ``run`` row aggregates total items so the
admin dashboard can show "this whole pipeline run touched N items".

``--until draft`` deliberately skips the standalone ``integrate`` step
because :func:`draft_issue` calls it internally — running it twice would
double the LLM bill for the importance scorer.
"""

from __future__ import annotations

from datetime import date as date_cls

import typer

from newsletter.core.db import session_scope
from newsletter.core.run_context import RunContext
from newsletter.slices.collection.service import collect_all
from newsletter.slices.integration.service import integrate
from newsletter.slices.monitoring.recorder import (
    build_embedding_client,
    build_llm_client,
    record_step,
)
from newsletter.slices.newsletter.assembler import draft_issue
from newsletter.slices.newsletter.audiences import AUDIENCES, DEFAULT_AUDIENCE
from newsletter.slices.processing.service import process

app = typer.Typer(
    name="run",
    help="Orchestrate collect → process → (integrate) → draft in one command.",
    invoke_without_command=True,
    no_args_is_help=False,
)

_STEPS: tuple[str, ...] = ("collect", "process", "integrate", "draft")


def _resolve_date(value: str) -> date_cls:
    if value == "today":
        return date_cls.today()
    return date_cls.fromisoformat(value)


def _resolve_until(value: str) -> str:
    if value not in _STEPS:
        raise typer.BadParameter(
            f"unknown step {value!r}. choose one of: {', '.join(_STEPS)}"
        )
    return value


def _validate_audience(value: str) -> str:
    if value not in AUDIENCES:
        raise typer.BadParameter(
            f"unknown audience {value!r}. choose one of: {', '.join(AUDIENCES)}"
        )
    return value


@app.callback(invoke_without_command=True)
def cmd_run(
    date: str = typer.Option("today", "--date", help="Issue date (YYYY-MM-DD or 'today')."),
    until: str = typer.Option(
        "draft",
        "--until",
        help=f"Stop after this step. One of: {', '.join(_STEPS)}.",
        callback=_resolve_until,
    ),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip all LLM-driven sub-steps."),
    audience: str = typer.Option(
        DEFAULT_AUDIENCE,
        "--audience",
        help=f"Audience profile (one of: {', '.join(AUDIENCES)}). Used by the draft step.",
        callback=_validate_audience,
    ),
    expert_count: int | None = typer.Option(
        None, "--expert-count", help="Override the audience's expert-track cap."
    ),
    practical_count: int | None = typer.Option(
        None, "--practical-count", help="Override the audience's practical-track cap."
    ),
) -> None:
    """Run the pipeline up to the chosen step."""
    issue_date = _resolve_date(date)
    llm = None if no_llm else build_llm_client()
    embedding_client = build_embedding_client()
    run_ctx = RunContext.new()
    typer.echo(f"Run id: {run_ctx.run_id}")
    typer.echo(f"Until: {until}")

    with record_step("run", meta={"date": issue_date.isoformat(), "until": until}) as run_log:
        total = 0

        # collect
        with record_step("collect", meta={"run_id": run_ctx.run_id}) as r:
            with session_scope() as session:
                rep = collect_all(session, run_context=run_ctx)
            r.item_count = rep.total_inserted
            total += r.item_count
            typer.echo(f"  collect: inserted={r.item_count}")
        if until == "collect":
            run_log.item_count = total
            return

        # process
        with record_step("process") as r:
            with session_scope() as session:
                rep = process(
                    session,
                    llm=llm,
                    keyword_only=no_llm,
                    embedding_client=embedding_client,
                )
            r.item_count = rep.processed
            total += r.item_count
            typer.echo(f"  process: processed={r.item_count}")
        if until == "process":
            run_log.item_count = total
            return

        # integrate is only run as a discrete step when it's the cutoff;
        # otherwise draft_issue will integrate internally.
        if until == "integrate":
            with record_step("integrate", meta={"audience": audience}) as r:
                with session_scope() as session:
                    rep = integrate(
                        session,
                        llm=llm,
                        # Integrate has no audience concept of its own; we
                        # pre-bind the audience's caps so the candidate
                        # counts match what draft would have used.
                        expert_count=expert_count or AUDIENCES[audience].expert_count,
                        practical_count=practical_count or AUDIENCES[audience].practical_count,
                    )
                r.item_count = len(rep.expert_candidates) + len(rep.practical_candidates)
                total += r.item_count
                typer.echo(f"  integrate: candidates={r.item_count}")
            run_log.item_count = total
            return

        # draft (calls integrate inside)
        with record_step(
            "draft",
            meta={"date": issue_date.isoformat(), "audience": audience},
        ) as r:
            with session_scope() as session:
                rep = draft_issue(
                    session,
                    today=issue_date,
                    llm=llm,
                    scoring_llm=llm,
                    audience=audience,
                    expert_count=expert_count,
                    practical_count=practical_count,
                )
            r.item_count = rep.candidate_count
            total += r.item_count
            typer.echo(
                f"  draft: issue_id={rep.issue_id} audience={rep.audience} "
                f"candidates={r.item_count}"
            )
        run_log.item_count = total
