"""``newsletter sources`` sub-commands.

Plan §22 wrote ``sources:list``; Typer's idiomatic equivalent is the
sub-app + command form (``newsletter sources list``).
"""

from __future__ import annotations

import json

import typer
from pydantic import ValidationError

from newsletter.core.db import session_scope
from newsletter.slices.sources import repository, seeds
from newsletter.slices.sources.schemas import SourceCreate, SourceRead

app = typer.Typer(
    name="sources",
    help="Manage the Source Registry.",
    no_args_is_help=True,
)


def _print_table(sources: list[SourceRead]) -> None:
    if not sources:
        typer.echo("(no sources)")
        return
    header = f"{'id':28} {'type':12} {'track':18} {'enabled':>7}  name"
    typer.echo(header)
    typer.echo("-" * len(header))
    for s in sources:
        typer.echo(
            f"{s.source_id:28} {s.type:12} {s.content_track:18} "
            f"{'yes' if s.enabled else 'no':>7}  {s.name}"
        )


@app.command("list")
def cmd_list(
    only_enabled: bool = typer.Option(False, "--enabled", help="Show only enabled sources."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
) -> None:
    """List configured sources."""
    with session_scope() as session:
        rows = repository.list_sources(session, only_enabled=only_enabled)
        out = [SourceRead.model_validate(r) for r in rows]
    if as_json:
        typer.echo(json.dumps([o.model_dump(mode="json") for o in out], indent=2))
    else:
        _print_table(out)


@app.command("show")
def cmd_show(source_id: str) -> None:
    """Show one source as JSON."""
    with session_scope() as session:
        row = repository.get(session, source_id)
        if row is None:
            typer.echo(f"Source not found: {source_id}", err=True)
            raise typer.Exit(code=1)
        out = SourceRead.model_validate(row)
    typer.echo(json.dumps(out.model_dump(mode="json"), indent=2))


@app.command("add")
def cmd_add(
    source_id: str = typer.Option(..., "--id"),
    name: str = typer.Option(...),
    type_: str = typer.Option(..., "--type", help="NAVER_API | RSS | YOUTUBE_RSS | API | MANUAL"),
    track: str = typer.Option(..., help="expert_news | practical_insight | both"),
    endpoint: str = typer.Option(...),
    query: str | None = typer.Option(None),
    priority: str = typer.Option("medium", help="high | medium | low"),
    trust_level: str = typer.Option("media", help="official | media | community"),
    fetch_interval: str = typer.Option("daily", help="hourly | daily | weekly"),
    language: str | None = typer.Option(None),
    region: str | None = typer.Option(None),
    category: str | None = typer.Option(None),
) -> None:
    """Add a new source."""
    try:
        payload = SourceCreate(
            source_id=source_id,
            name=name,
            type=type_,  # type: ignore[arg-type]
            content_track=track,  # type: ignore[arg-type]
            endpoint=endpoint,
            query=query,
            priority=priority,  # type: ignore[arg-type]
            trust_level=trust_level,  # type: ignore[arg-type]
            fetch_interval=fetch_interval,  # type: ignore[arg-type]
            language=language,
            region=region,
            category=category,
        )
    except ValidationError as exc:
        typer.echo(f"Invalid input:\n{exc}", err=True)
        raise typer.Exit(code=2) from exc

    with session_scope() as session:
        try:
            repository.add(session, payload)
        except repository.SourceAlreadyExistsError as exc:
            typer.echo(f"Source already exists: {source_id}", err=True)
            raise typer.Exit(code=1) from exc
    typer.echo(f"Added source: {source_id}")


@app.command("disable")
def cmd_disable(source_id: str) -> None:
    """Disable a source (will be skipped by collection)."""
    with session_scope() as session:
        try:
            repository.disable(session, source_id)
        except repository.SourceNotFoundError as exc:
            typer.echo(f"Source not found: {source_id}", err=True)
            raise typer.Exit(code=1) from exc
    typer.echo(f"Disabled: {source_id}")


@app.command("enable")
def cmd_enable(source_id: str) -> None:
    """Enable a previously-disabled source."""
    with session_scope() as session:
        try:
            repository.enable(session, source_id)
        except repository.SourceNotFoundError as exc:
            typer.echo(f"Source not found: {source_id}", err=True)
            raise typer.Exit(code=1) from exc
    typer.echo(f"Enabled: {source_id}")


@app.command("seed")
def cmd_seed() -> None:
    """Insert (or update) the initial set of curated sources."""
    with session_scope() as session:
        created, updated = seeds.seed(session)
    typer.echo(f"Seed complete: {created} created, {updated} updated.")
