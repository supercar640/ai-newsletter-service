"""``newsletter monthly`` — monthly AI digest.

Aggregates trends + competitor mentions + importance-ranked top items for a
calendar month, optionally adds an LLM narrative (skipped when no API key or
``--no-narrative``), and prints/saves markdown or HTML.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date as date_cls
from pathlib import Path

import typer

from newsletter.core.config import get_settings
from newsletter.core.db import session_scope
from newsletter.core.report_html import render_report_html
from newsletter.slices.monitoring.recorder import build_llm_client
from newsletter.slices.monthly.narrative import build_narrative
from newsletter.slices.monthly.report import render_markdown
from newsletter.slices.monthly.service import build_monthly_report

app = typer.Typer(
    name="monthly",
    help="Monthly AI digest: trends + competitors + top items + LLM narrative.",
    invoke_without_command=True,
    no_args_is_help=False,
)


def _resolve_month(value: str | None) -> date_cls | None:
    if not value:
        return None
    return date_cls.fromisoformat(f"{value}-01")


@app.callback(invoke_without_command=True)
def cmd_monthly(
    month: str | None = typer.Option(
        None, "--month", help="Target month YYYY-MM (default: last completed month)."
    ),
    top: int = typer.Option(10, "--top", help="Max headlines in the 주요 기사 section."),
    no_narrative: bool = typer.Option(
        False, "--no-narrative", help="Skip the LLM narrative section."
    ),
    fmt: str = typer.Option("md", "--format", help="md or html."),
    save: str | None = typer.Option(
        None, "--save", help="Write the report to this path instead of stdout."
    ),
) -> None:
    """Print (or save) the monthly AI digest."""
    if fmt not in ("md", "html"):
        typer.echo("format must be 'md' or 'html'", err=True)
        raise typer.Exit(code=1)
    try:
        target = _resolve_month(month)
    except ValueError:
        typer.echo("month must be YYYY-MM", err=True)
        raise typer.Exit(code=1) from None

    with session_scope() as session:
        report = build_monthly_report(session, month=target, top_k=top)

    if not no_narrative and get_settings().anthropic_api_key:
        report = replace(report, narrative=build_narrative(report, llm=build_llm_client()))

    markdown = render_markdown(report)
    output = (
        render_report_html(markdown, title=f"{report.month} AI 동향 리포트")
        if fmt == "html"
        else markdown
    )
    if save:
        Path(save).write_text(output, encoding="utf-8")
        typer.echo(f"월간 리포트 저장: {save}")
    else:
        typer.echo(output)
