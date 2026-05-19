"""Newsletter draft CLI — `newsletter draft`."""

from __future__ import annotations

from datetime import date as date_cls

import typer

from newsletter.core.db import session_scope
from newsletter.slices.monitoring.recorder import build_llm_client, record_step
from newsletter.slices.newsletter.assembler import draft_issue

app = typer.Typer(
    help="Newsletter draft commands.",
    no_args_is_help=True,
    add_completion=False,
)


def _resolve_date(value: str) -> date_cls:
    if value == "today":
        return date_cls.today()
    return date_cls.fromisoformat(value)


@app.command()
def draft(
    date: str = typer.Option("today", "--date", help="Issue date (YYYY-MM-DD or 'today')."),
    expert_count: int = typer.Option(7, help="Max expert-track candidates."),
    practical_count: int = typer.Option(4, help="Max practical-track candidates."),
) -> None:
    """Generate today's newsletter draft and store it as a NewsletterIssue."""
    issue_date = _resolve_date(date)
    llm = build_llm_client()
    with record_step("draft", meta={"date": issue_date.isoformat()}) as run_log:
        with session_scope() as session:
            report = draft_issue(
                session,
                today=issue_date,
                llm=llm,
                scoring_llm=llm,
                expert_count=expert_count,
                practical_count=practical_count,
            )
        run_log.item_count = report.candidate_count
    typer.echo(
        f"Draft issue {report.issue_id} created for {report.issue_date.isoformat()} "
        f"({report.expert_clusters_used} expert / {report.practical_clusters_used} practical clusters)."
    )
