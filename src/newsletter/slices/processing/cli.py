"""``newsletter process`` command — turn RawItem into ProcessedItem."""

from __future__ import annotations

import typer

from newsletter.core.db import session_scope
from newsletter.slices.monitoring.recorder import (
    build_embedding_client,
    build_llm_client,
    record_step,
)
from newsletter.slices.processing.service import ProcessingReport, process

app = typer.Typer(
    name="process",
    help="Normalize, dedupe, classify track, and admit AI-relevant items.",
    invoke_without_command=True,
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def cmd_process(
    date: str = typer.Option(
        "today",
        "--date",
        help="Run label (informational). Processing is idempotent.",
    ),
    keyword_only: bool = typer.Option(
        False,
        "--keyword-only",
        help="Skip LLM relevance / track calls (cheaper, less accurate).",
    ),
    min_relevance: float = typer.Option(
        0.0,
        "--min-relevance",
        help="Drop items whose final relevance score is below this threshold.",
    ),
) -> None:
    """Process pending RawItem rows into ProcessedItem rows."""
    _ = date
    llm = None if keyword_only else build_llm_client()
    embedding_client = build_embedding_client()
    with record_step("process") as run_log:
        with session_scope() as session:
            report = process(
                session,
                llm=llm,
                keyword_only=keyword_only,
                min_relevance=min_relevance,
                embedding_client=embedding_client,
            )
        run_log.item_count = report.processed
    _print_report(report)
    if report.errors:
        raise typer.Exit(code=1)


def _print_report(report: ProcessingReport) -> None:
    typer.echo(f"Fetched: {report.fetched}")
    typer.echo(f"Processed: {report.processed}")
    typer.echo(f"Filtered out (not AI-related): {report.filtered_out}")
    if report.per_track:
        for track, count in sorted(report.per_track.items()):
            typer.echo(f"  {track}: {count}")
    if report.errors:
        typer.echo("Errors:")
        for raw_id, msg in report.errors:
            typer.echo(f"  raw_item_id={raw_id}: {msg}")
