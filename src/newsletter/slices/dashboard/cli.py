"""``newsletter dashboard`` — source performance + quality metrics.

Deterministic report over collected/processed items in a look-back window.
No LLM. Complements ``newsletter stats`` (operational/cost).
"""

from __future__ import annotations

from datetime import date as date_cls
from pathlib import Path

import typer

from newsletter.core.db import session_scope
from newsletter.core.report_html import render_report_html
from newsletter.slices.dashboard.report import render_markdown
from newsletter.slices.dashboard.service import build_dashboard

app = typer.Typer(
    name="dashboard",
    help="Source performance + quality metrics over collected/processed items.",
    invoke_without_command=True,
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def cmd_dashboard(
    days: int = typer.Option(30, "--days", help="Look-back window length in days."),
    since: str | None = typer.Option(
        None, "--since", help="Window start YYYY-MM-DD (wins over --days)."
    ),
    until: str | None = typer.Option(
        None, "--until", help="Exclusive window end YYYY-MM-DD (default tomorrow)."
    ),
    top: int = typer.Option(10, "--top", help="Max categories in the 상위 카테고리 table."),
    fmt: str = typer.Option("md", "--format", help="md or html."),
    save: str | None = typer.Option(
        None, "--save", help="Write the report to this path instead of stdout."
    ),
) -> None:
    """Print (or save) the performance dashboard."""
    if fmt not in ("md", "html"):
        typer.echo("format must be 'md' or 'html'", err=True)
        raise typer.Exit(code=1)
    since_date = date_cls.fromisoformat(since) if since else None
    until_date = date_cls.fromisoformat(until) if until else None
    with session_scope() as session:
        report = build_dashboard(
            session, days=days, until=until_date, since=since_date, top_categories=top
        )

    markdown = render_markdown(report)
    output = render_report_html(markdown, title="성과 대시보드") if fmt == "html" else markdown
    if save:
        Path(save).write_text(output, encoding="utf-8")
        typer.echo(f"대시보드 저장: {save}")
    else:
        typer.echo(output)
