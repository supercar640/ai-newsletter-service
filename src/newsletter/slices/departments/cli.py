"""``newsletter departments`` — operator CRUD for the department registry.

Registered departments drive the per-department "부서별 활용 팁" section: each
enabled row gets one tailored tip per issue, and past tips are accumulated to
keep successive issues varied.
"""

from __future__ import annotations

import typer

from newsletter.core.db import session_scope
from newsletter.slices.departments import repository
from newsletter.slices.departments.schemas import DepartmentCreate, DepartmentUpdate
from newsletter.slices.departments.seeds import seed as seed_departments

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
            row = repository.add(
                session, DepartmentCreate(name=name, description=description)
            )
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
            row = repository.update(
                session, department_id, DepartmentUpdate(enabled=True)
            )
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
