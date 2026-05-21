"""``newsletter corpus`` — index internal company documents for scoring.

``corpus index`` scans ``COMPANY_CONTEXT_DIR`` and (re)indexes changed files.
When ``VOYAGE_API_KEY`` is unset, chunks store keywords only and the importance
boost falls back to keyword overlap.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer

from newsletter.core.config import get_settings
from newsletter.core.db import session_scope
from newsletter.slices.corpus import repository
from newsletter.slices.corpus.indexer import index_corpus
from newsletter.slices.monitoring.recorder import build_embedding_client

app = typer.Typer(
    help="Index internal company documents that boost importance scoring.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command("index")
def cmd_index() -> None:
    """Scan COMPANY_CONTEXT_DIR and (re)index changed documents."""
    # company_context_dir is added in Task 8; until then read the raw env var.
    context_dir = getattr(get_settings(), "company_context_dir", "") or os.environ.get(
        "COMPANY_CONTEXT_DIR", ""
    )
    if not context_dir:
        typer.echo(
            "COMPANY_CONTEXT_DIR 가 설정되지 않았습니다. 인덱싱을 건너뜁니다.",
            err=True,
        )
        return
    root = Path(context_dir)
    if not root.is_dir():
        typer.echo(f"디렉터리가 없습니다: {root}", err=True)
        raise typer.Exit(code=1)

    client = build_embedding_client()
    with session_scope() as session:
        report = index_corpus(session, root=root, embed_client=client)
    typer.echo(
        f"corpus index 완료: scanned={report.scanned} indexed={report.indexed} "
        f"skipped={report.skipped} chunks={report.chunks} embedded={report.embedded}"
    )


@app.command("list")
def cmd_list() -> None:
    """Show indexed chunks grouped by file."""
    with session_scope() as session:
        rows = repository.list_chunks(session)
        if not rows:
            typer.echo("(no chunks indexed)")
            return
        by_file: dict[str, list] = {}
        for row in rows:
            by_file.setdefault(row.source_path, []).append(row)
        typer.echo(f"{'chunks':>7} {'embed':>5}  file")
        typer.echo("-" * 40)
        for path, chunks in sorted(by_file.items()):
            embedded = sum(1 for c in chunks if c.embedding is not None)
            typer.echo(f"{len(chunks):>7} {embedded:>5}  {path}")


@app.command("clear")
def cmd_clear() -> None:
    """Delete every indexed chunk. Irreversible."""
    with session_scope() as session:
        deleted = repository.delete_all(session)
    typer.echo(f"corpus clear 완료: {deleted} chunks 삭제")


@app.command("status")
def cmd_status() -> None:
    """Compare COMPANY_CONTEXT_DIR against the indexed state."""
    settings = get_settings()
    has_key = bool(settings.voyage_api_key)
    typer.echo(f"embedding key: {'있음' if has_key else '없음 (키워드 폴백)'}")
    context_dir = getattr(settings, "company_context_dir", "") or os.environ.get(
        "COMPANY_CONTEXT_DIR", ""
    )
    if not context_dir:
        typer.echo("COMPANY_CONTEXT_DIR: (미설정)")
        return
    root = Path(context_dir)
    typer.echo(f"COMPANY_CONTEXT_DIR: {root}")
    with session_scope() as session:
        stored = repository.file_hashes(session)
    typer.echo(f"indexed files: {len(stored)}")
