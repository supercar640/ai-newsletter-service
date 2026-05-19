"""``newsletter integrate`` command — score, cluster, pick candidates."""

from __future__ import annotations

import typer

from newsletter.core.db import session_scope
from newsletter.slices.integration.candidates import Candidate
from newsletter.slices.integration.service import IntegrationReport, integrate
from newsletter.slices.monitoring.recorder import build_llm_client, record_step

app = typer.Typer(
    name="integrate",
    help="Score, cluster, and pick per-track candidates from ProcessedItem rows.",
    invoke_without_command=True,
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def cmd_integrate(
    date: str = typer.Option(
        "today",
        "--date",
        help="Run label (informational). Integration is idempotent on importance_score.",
    ),
    no_llm: bool = typer.Option(
        False,
        "--no-llm",
        help="Skip the LLM importance scorer (use trust x recency only).",
    ),
    expert_count: int = typer.Option(
        7,
        "--expert-count",
        help="Max candidates to emit for the expert_news track.",
    ),
    practical_count: int = typer.Option(
        4,
        "--practical-count",
        help="Max candidates to emit for the practical_insight track.",
    ),
    top_k_for_llm: int = typer.Option(
        20,
        "--top-k-for-llm",
        help="Number of highest-base-score items to send to the LLM scorer.",
    ),
    max_per_category: int = typer.Option(
        2,
        "--max-per-category",
        help="Soft cap on items sharing the same category in each track.",
    ),
) -> None:
    """Score every ProcessedItem, cluster duplicates, output candidate lists."""
    _ = date
    llm = None if no_llm else build_llm_client()
    with record_step("integrate") as run_log:
        with session_scope() as session:
            report = integrate(
                session,
                llm=llm,
                expert_count=expert_count,
                practical_count=practical_count,
                top_k_for_llm=top_k_for_llm,
                max_per_category=max_per_category,
            )
        run_log.item_count = len(report.expert_candidates) + len(report.practical_candidates)
    _print_report(report)


def _print_report(report: IntegrationReport) -> None:
    typer.echo(f"Scored: {report.scored}")
    typer.echo(f"Clusters: {report.clusters}")
    typer.echo(f"Expert candidates: {len(report.expert_candidates)}")
    for c in report.expert_candidates:
        typer.echo(f"  {_format_candidate(c)}")
    typer.echo(f"Practical candidates: {len(report.practical_candidates)}")
    for c in report.practical_candidates:
        typer.echo(f"  {_format_candidate(c)}")


def _format_candidate(c: Candidate) -> str:
    members = (
        f" (+{len(c.cluster_member_ids) - 1} cluster mates)"
        if len(c.cluster_member_ids) > 1
        else ""
    )
    return (
        f"#{c.id} score={c.score:.3f} category={c.category or '-'} cluster={c.cluster_id}{members}"
    )
