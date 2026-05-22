"""``newsletter competitors`` — registry CRUD + mention report.

Deterministic alias matching over accumulated items. No LLM, no embeddings.
"""

from __future__ import annotations

from datetime import date as date_cls
from pathlib import Path

import typer

from newsletter.core.db import session_scope
from newsletter.core.report_html import render_report_html
from newsletter.slices.competitors import repository
from newsletter.slices.competitors.report import render_markdown
from newsletter.slices.competitors.schemas import CompetitorCreate, CompetitorUpdate
from newsletter.slices.competitors.service import analyze_competitors

app = typer.Typer(
    help="Track competitor mentions across collected items.",
    no_args_is_help=True,
    add_completion=False,
)


def _split_aliases(value: str | None) -> list[str]:
    if not value:
        return []
    return [a.strip() for a in value.split(",") if a.strip()]


@app.command("list")
def cmd_list() -> None:
    """List registered competitors."""
    with session_scope() as session:
        rows = repository.list_competitors(session)
        if not rows:
            typer.echo("(no competitors registered)")
            return
        header = f"{'id':>4} {'enabled':>8}  name / aliases"
        typer.echo(header)
        typer.echo("-" * len(header))
        for r in rows:
            aliases = ", ".join(repository.load_aliases(r))
            typer.echo(f"{r.id:>4} {('on' if r.enabled else 'off'):>8}  {r.name}  [{aliases}]")


@app.command("add")
def cmd_add(
    name: str = typer.Option(..., "--name", help="Display name (unique)."),
    aliases: str = typer.Option(
        "", "--aliases", help="Comma-separated aliases / product names to match."
    ),
) -> None:
    """Register a competitor."""
    payload = CompetitorCreate(name=name, aliases=_split_aliases(aliases))
    with session_scope() as session:
        try:
            row = repository.add(session, payload)
        except repository.CompetitorAlreadyExistsError:
            typer.echo(f"이미 존재하는 이름입니다: {name}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"competitor 추가 완료: id={row.id} name={row.name}")


@app.command("disable")
def cmd_disable(
    competitor_id: int = typer.Argument(..., help="Competitor id to disable."),
) -> None:
    """Disable a competitor (excluded from detection)."""
    with session_scope() as session:
        try:
            row = repository.disable(session, competitor_id)
        except repository.CompetitorNotFoundError:
            typer.echo(f"존재하지 않는 id: {competitor_id}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"competitor 비활성화: id={row.id} name={row.name}")


@app.command("enable")
def cmd_enable(
    competitor_id: int = typer.Argument(..., help="Competitor id."),
) -> None:
    """Re-enable a previously disabled competitor."""
    with session_scope() as session:
        try:
            row = repository.update(session, competitor_id, CompetitorUpdate(enabled=True))
        except repository.CompetitorNotFoundError:
            typer.echo(f"존재하지 않는 id: {competitor_id}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"competitor 활성화: id={row.id} name={row.name}")


@app.command("remove")
def cmd_remove(
    competitor_id: int = typer.Argument(..., help="Competitor id to remove."),
) -> None:
    """Delete a competitor. Irreversible."""
    with session_scope() as session:
        try:
            repository.remove(session, competitor_id)
        except repository.CompetitorNotFoundError:
            typer.echo(f"존재하지 않는 id: {competitor_id}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"competitor 삭제 완료: id={competitor_id}")


@app.command("report")
def cmd_report(
    days: int = typer.Option(7, "--days", help="Look-back window length in days."),
    since: str | None = typer.Option(
        None, "--since", help="Window start YYYY-MM-DD (wins over --days)."
    ),
    until: str | None = typer.Option(
        None, "--until", help="Exclusive window end YYYY-MM-DD (default tomorrow)."
    ),
    top: int = typer.Option(5, "--top", help="Max headlines per competitor."),
    fmt: str = typer.Option("md", "--format", help="md or html."),
    save: str | None = typer.Option(
        None, "--save", help="Write the report to this path instead of stdout."
    ),
) -> None:
    """Print (or save) the competitor mention report."""
    if fmt not in ("md", "html"):
        typer.echo("format must be 'md' or 'html'", err=True)
        raise typer.Exit(code=1)
    since_date = date_cls.fromisoformat(since) if since else None
    until_date = date_cls.fromisoformat(until) if until else None
    with session_scope() as session:
        if not repository.list_competitors(session, only_enabled=True):
            typer.echo("(no competitors registered)")
            return
        report = analyze_competitors(
            session, days=days, until=until_date, since=since_date, top_k=top
        )

    markdown = render_markdown(report)
    output = render_report_html(markdown, title="경쟁사 멘션 리포트") if fmt == "html" else markdown
    if save:
        Path(save).write_text(output, encoding="utf-8")
        typer.echo(f"경쟁사 리포트 저장: {save}")
    else:
        typer.echo(output)
