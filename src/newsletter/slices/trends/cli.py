"""``newsletter trends`` — period-over-period title-keyword trend report.

Deterministic: counts distinct title terms across two equal-length windows
(current vs previous) and prints rising/fading/new/dropped terms. No LLM.
"""

from __future__ import annotations

from datetime import date as date_cls
from pathlib import Path

import typer

from newsletter.core.db import session_scope
from newsletter.slices.trends.report import render_markdown
from newsletter.slices.trends.service import analyze_trends

app = typer.Typer(
    name="trends",
    help="Period-over-period AI topic trend report from accumulated items.",
    invoke_without_command=True,
    no_args_is_help=False,
)


def _resolve_end(value: str | None) -> date_cls:
    if value is None or value == "today":
        return date_cls.today()
    return date_cls.fromisoformat(value)


@app.callback(invoke_without_command=True)
def cmd_trends(
    period: str = typer.Option("week", "--period", help="week or month."),
    end: str | None = typer.Option(
        None, "--end", help="End date YYYY-MM-DD or 'today' (default today)."
    ),
    top: int = typer.Option(15, "--top", help="Max terms per section."),
    min_count: int = typer.Option(
        2, "--min-count", help="Ignore terms below this article count."
    ),
    save: str | None = typer.Option(
        None, "--save", help="Write markdown to this path instead of stdout."
    ),
) -> None:
    """Print (or save) the period-over-period trend report."""
    if period not in ("week", "month"):
        typer.echo("period must be 'week' or 'month'", err=True)
        raise typer.Exit(code=1)
    with session_scope() as session:
        report = analyze_trends(
            session, period=period, end=_resolve_end(end), top_n=top, min_count=min_count
        )

    if report.total_current_items == 0 and report.total_previous_items == 0:
        typer.echo("(no items in window)")
        return

    markdown = render_markdown(report)
    if save:
        Path(save).write_text(markdown, encoding="utf-8")
        typer.echo(f"트렌드 리포트 저장: {save}")
    else:
        typer.echo(markdown)
