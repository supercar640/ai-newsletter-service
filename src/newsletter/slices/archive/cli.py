"""``newsletter archive`` — push sent newsletter issues to Notion."""

from __future__ import annotations

import typer

from newsletter.core.db import session_scope
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.archive.notion_client import NotionClient, NotionError
from newsletter.slices.archive.service import (
    AlreadyArchivedError,
    ArchiveDisabledError,
    archive_issue,
    backfill_archive,
)

app = typer.Typer(
    help="Archive sent newsletter issues to Notion.",
    no_args_is_help=True,
    add_completion=False,
)


def _build_client() -> NotionClient | None:
    return NotionClient.from_settings()


@app.command("issue")
def cmd_issue(
    issue_id: int = typer.Argument(..., help="NewsletterIssue id."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-archive even if the issue already has a notion_page_id.",
    ),
) -> None:
    """Archive a single issue."""
    client = _build_client()
    with session_scope() as session:
        issue = session.get(NewsletterIssue, issue_id)
        if issue is None:
            typer.echo(f"issue {issue_id} 를 찾을 수 없습니다.", err=True)
            raise typer.Exit(code=1)
        try:
            report = archive_issue(session, issue, client=client, force=force)
        except ArchiveDisabledError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except AlreadyArchivedError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except NotionError as exc:
            typer.echo(f"Notion 호출 실패: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    typer.echo(f"아카이브 완료: issue={report.issue_id} page_id={report.page_id}")


@app.command("backfill")
def cmd_backfill() -> None:
    """Archive every sent issue that does not yet have a Notion page."""
    client = _build_client()
    with session_scope() as session:
        try:
            report = backfill_archive(session, client=client)
        except ArchiveDisabledError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

    typer.echo(
        f"아카이브: 신규={report.archived_count}, 스킵={report.skipped_count}, "
        f"오류={len(report.errors)}"
    )
    for issue_id, msg in report.errors:
        typer.echo(f"  issue={issue_id}: {msg}", err=True)
    if report.errors:
        raise typer.Exit(code=1)
