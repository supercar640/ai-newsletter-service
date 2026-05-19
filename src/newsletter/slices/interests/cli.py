"""``newsletter interests`` — operator CRUD for company-interest rows.

Adding an interest is the trigger that asks the embedding provider for a
vector — when ``VOYAGE_API_KEY`` is unset the description embedding stays
NULL and only keyword matching contributes to the importance boost.
"""

from __future__ import annotations

import typer

from newsletter.core.db import session_scope
from newsletter.core.embeddings import serialize
from newsletter.slices.interests import repository
from newsletter.slices.interests.schemas import InterestCreate, InterestUpdate
from newsletter.slices.monitoring.recorder import build_embedding_client

app = typer.Typer(
    help="Manage company-interest topics that boost importance scoring.",
    no_args_is_help=True,
    add_completion=False,
)


def _split_keywords(value: str | None) -> list[str]:
    if not value:
        return []
    return [k.strip() for k in value.split(",") if k.strip()]


@app.command("list")
def cmd_list(
    only_enabled: bool = typer.Option(
        False,
        "--enabled-only",
        help="Show only enabled interests.",
    ),
) -> None:
    """List registered company interests."""
    with session_scope() as session:
        rows = repository.list_interests(session, only_enabled=only_enabled)
    if not rows:
        typer.echo("(no interests registered)")
        return
    header = f"{'id':>4} {'enabled':>8} {'weight':>7} {'embed':>5}  name / keywords"
    typer.echo(header)
    typer.echo("-" * len(header))
    for r in rows:
        keywords = ", ".join(repository.load_keywords(r))
        typer.echo(
            f"{r.id:>4} {('on' if r.enabled else 'off'):>8} {r.weight:>7.2f} "
            f"{('y' if r.embedding else 'n'):>5}  {r.name}  [{keywords}]"
        )


@app.command("add")
def cmd_add(
    name: str = typer.Option(..., "--name", help="Display name (unique)."),
    description: str | None = typer.Option(
        None, "--description", help="Free-text description (used for embedding)."
    ),
    keywords: str = typer.Option(
        "",
        "--keywords",
        help="Comma-separated keywords for fast lexical matching.",
    ),
    weight: float = typer.Option(
        1.0, "--weight", min=0.0, max=5.0, help="Weight in [0, 5]."
    ),
) -> None:
    """Add an interest. Generates an embedding from --description when possible."""
    payload = InterestCreate(
        name=name,
        description=description,
        keywords=_split_keywords(keywords),
        weight=weight,
    )
    with session_scope() as session:
        try:
            row = repository.add(session, payload)
        except repository.InterestAlreadyExistsError:
            typer.echo(f"이미 존재하는 이름입니다: {name}", err=True)
            raise typer.Exit(code=1) from None

        if description:
            client = build_embedding_client()
            vectors = client.embed([description])
            if vectors:
                repository.set_embedding(
                    session,
                    row.id,
                    vector_bytes=serialize(vectors[0]),
                    model=getattr(client, "model", "unknown"),
                )

        typer.echo(f"interest 추가 완료: id={row.id} name={row.name}")


@app.command("disable")
def cmd_disable(
    interest_id: int = typer.Argument(..., help="Interest id to disable."),
) -> None:
    """Disable an interest (scoring will skip it)."""
    with session_scope() as session:
        try:
            row = repository.disable(session, interest_id)
        except repository.InterestNotFoundError:
            typer.echo(f"존재하지 않는 id: {interest_id}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"interest 비활성화: id={row.id} name={row.name}")


@app.command("enable")
def cmd_enable(interest_id: int = typer.Argument(..., help="Interest id.")) -> None:
    """Re-enable a previously disabled interest."""
    with session_scope() as session:
        try:
            row = repository.update(
                session, interest_id, InterestUpdate(enabled=True)
            )
        except repository.InterestNotFoundError:
            typer.echo(f"존재하지 않는 id: {interest_id}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"interest 활성화: id={row.id} name={row.name}")


@app.command("remove")
def cmd_remove(
    interest_id: int = typer.Argument(..., help="Interest id to remove."),
) -> None:
    """Delete an interest. Irreversible."""
    with session_scope() as session:
        try:
            repository.remove(session, interest_id)
        except repository.InterestNotFoundError:
            typer.echo(f"존재하지 않는 id: {interest_id}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"interest 삭제 완료: id={interest_id}")
