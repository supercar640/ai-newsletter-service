"""``newsletter collect`` command — run the collection pipeline."""

from __future__ import annotations

import typer

from newsletter.core.db import session_scope
from newsletter.core.run_context import RunContext
from newsletter.slices.collection.service import CollectionReport, collect_all

app = typer.Typer(
    name="collect",
    help="Fetch items from enabled sources into the RawItem table.",
    invoke_without_command=True,
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def cmd_collect(
    date: str = typer.Option(
        "today",
        "--date",
        help="Run label (informational). Collection is incremental either way.",
    ),
    source_id: list[str] | None = typer.Option(
        None,
        "--source-id",
        "-s",
        help="Restrict to one or more source ids. Repeat the flag for multiple.",
    ),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Reuse a specific run directory id (default: new timestamp).",
    ),
) -> None:
    """Collect from all enabled sources (or the subset filtered by ``--source-id``)."""
    _ = date  # informational
    run_ctx = RunContext.new(run_id=run_id)
    typer.echo(f"Run id: {run_ctx.run_id}")
    typer.echo(f"Artifacts: {run_ctx.path}")

    with session_scope() as session:
        report = collect_all(session, source_ids=source_id or None, run_context=run_ctx)

    _print_report(report)
    if report.errors:
        raise typer.Exit(code=1)


def _print_report(report: CollectionReport) -> None:
    if not report.per_source:
        typer.echo("(no enabled sources to collect)")
        return

    header = f"{'source':28} {'fetched':>8} {'inserted':>9} {'dup':>5}  status"
    typer.echo(header)
    typer.echo("-" * len(header))
    for s in report.per_source:
        status = "ERR: " + s.error if s.error else "ok"
        typer.echo(
            f"{s.source_id:28} {s.fetched:>8} {s.inserted:>9} {s.skipped_duplicate:>5}  {status}"
        )
    typer.echo("-" * len(header))
    typer.echo(
        f"Total: {report.total_fetched} fetched, {report.total_inserted} inserted, "
        f"{report.total_duplicates} duplicate, {len(report.errors)} errors."
    )
