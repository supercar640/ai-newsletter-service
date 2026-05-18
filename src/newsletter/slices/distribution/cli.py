"""Distribution CLI — `newsletter send --issue ID [--dry-run]`."""

from __future__ import annotations

import typer

from newsletter.core.db import session_scope
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.distribution.service import SendError, send_issue

app = typer.Typer(
    help="Send a NewsletterIssue via SMTP.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def send(
    issue: int = typer.Option(..., "--issue", help="NewsletterIssue id."),
    dry_run: bool = typer.Option(
        False, "--dry-run/--no-dry-run", help="Simulate without contacting SMTP."
    ),
) -> None:
    """Send an approved newsletter issue."""
    with session_scope() as session:
        row = session.get(NewsletterIssue, issue)
        if row is None:
            typer.echo(f"이슈 {issue} 를 찾을 수 없습니다.", err=True)
            raise typer.Exit(code=1)
        try:
            report = send_issue(session, row, dry_run=dry_run)
        except SendError as exc:
            typer.echo(f"발송 실패: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    if report.dry_run:
        typer.echo(f"[DRY-RUN] {len(report.recipients)}명에게 발송 시뮬레이션 완료.")
    else:
        typer.echo(f"발송 완료: {len(report.recipients)}명, sent_at={report.sent_at.isoformat()}")
