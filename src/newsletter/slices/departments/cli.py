"""``newsletter departments`` — operator CRUD for the department registry.

Registered departments drive the per-department "부서별 활용 팁" section: each
enabled row gets one tailored tip per issue, and past tips are accumulated to
keep successive issues varied.
"""

from __future__ import annotations

from datetime import date as date_cls
from pathlib import Path

import typer

from newsletter.core.db import session_scope
from newsletter.core.report_html import render_report_html
from newsletter.slices.departments import repository
from newsletter.slices.departments.digest import build_department_digest
from newsletter.slices.departments.report import render_markdown
from newsletter.slices.departments.schemas import DepartmentCreate, DepartmentUpdate
from newsletter.slices.departments.seeds import seed as seed_departments
from newsletter.slices.monitoring.recorder import build_embedding_client

app = typer.Typer(
    help="Manage departments for the per-department usage-tips section.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command("list")
def cmd_list(
    only_enabled: bool = typer.Option(
        False, "--enabled-only", help="Show only enabled departments."
    ),
) -> None:
    """List registered departments."""
    with session_scope() as session:
        rows = repository.list_departments(session, only_enabled=only_enabled)
    if not rows:
        typer.echo("(no departments registered)")
        return
    header = f"{'id':>4} {'enabled':>8}  name  /  description"
    typer.echo(header)
    typer.echo("-" * len(header))
    for r in rows:
        typer.echo(
            f"{r.id:>4} {('on' if r.enabled else 'off'):>8}  {r.name}  /  {r.description or ''}"
        )


@app.command("add")
def cmd_add(
    name: str = typer.Option(..., "--name", help="Department name (unique)."),
    description: str | None = typer.Option(
        None, "--description", help="Work characteristics (used as tip context)."
    ),
) -> None:
    """Add a department."""
    with session_scope() as session:
        try:
            row = repository.add(session, DepartmentCreate(name=name, description=description))
        except repository.DepartmentAlreadyExistsError:
            typer.echo(f"이미 존재하는 이름입니다: {name}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"department 추가 완료: id={row.id} name={row.name}")


@app.command("disable")
def cmd_disable(
    department_id: int = typer.Argument(..., help="Department id to disable."),
) -> None:
    """Disable a department (tips generation will skip it)."""
    with session_scope() as session:
        try:
            row = repository.disable(session, department_id)
        except repository.DepartmentNotFoundError:
            typer.echo(f"존재하지 않는 id: {department_id}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"department 비활성화: id={row.id} name={row.name}")


@app.command("enable")
def cmd_enable(
    department_id: int = typer.Argument(..., help="Department id."),
) -> None:
    """Re-enable a previously disabled department."""
    with session_scope() as session:
        try:
            row = repository.update(session, department_id, DepartmentUpdate(enabled=True))
        except repository.DepartmentNotFoundError:
            typer.echo(f"존재하지 않는 id: {department_id}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"department 활성화: id={row.id} name={row.name}")


@app.command("remove")
def cmd_remove(
    department_id: int = typer.Argument(..., help="Department id to remove."),
) -> None:
    """Delete a department. Irreversible."""
    with session_scope() as session:
        try:
            repository.remove(session, department_id)
        except repository.DepartmentNotFoundError:
            typer.echo(f"존재하지 않는 id: {department_id}", err=True)
            raise typer.Exit(code=1) from None
        typer.echo(f"department 삭제 완료: id={department_id}")


@app.command("seed")
def cmd_seed() -> None:
    """Seed the default departments (idempotent)."""
    with session_scope() as session:
        created, updated = seed_departments(session)
    typer.echo(f"department 시드 완료: 신규={created}, 갱신={updated}")


@app.command("digest")
def cmd_digest(
    days: int = typer.Option(7, "--days", help="Look-back window length in days."),
    since: str | None = typer.Option(
        None, "--since", help="Window start YYYY-MM-DD (wins over --days)."
    ),
    until: str | None = typer.Option(
        None, "--until", help="Exclusive window end YYYY-MM-DD (default tomorrow)."
    ),
    top: int = typer.Option(5, "--top", help="Max headlines per department."),
    fmt: str = typer.Option("md", "--format", help="md or html."),
    save: str | None = typer.Option(
        None, "--save", help="Write the report to this path instead of stdout."
    ),
) -> None:
    """Per-department most-relevant articles (embedding match, keyword fallback)."""
    if fmt not in ("md", "html"):
        typer.echo("format must be 'md' or 'html'", err=True)
        raise typer.Exit(code=1)
    since_date = date_cls.fromisoformat(since) if since else None
    until_date = date_cls.fromisoformat(until) if until else None
    with session_scope() as session:
        digest = build_department_digest(
            session,
            days=days,
            until=until_date,
            since=since_date,
            top_k=top,
            embed_client=build_embedding_client(),
        )

    markdown = render_markdown(digest)
    output = render_report_html(markdown, title="부서별 다이제스트") if fmt == "html" else markdown
    if save:
        Path(save).write_text(output, encoding="utf-8")
        typer.echo(f"부서별 다이제스트 저장: {save}")
    else:
        typer.echo(output)
