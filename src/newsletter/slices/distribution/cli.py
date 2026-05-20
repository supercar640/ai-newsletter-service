"""Distribution CLI.

* ``newsletter send --issue ID [--dry-run]``  — email via SMTP.
* ``newsletter slack --issue ID [--dry-run] [--force]`` — Slack summary card.
"""

from __future__ import annotations

import typer

from newsletter.core.db import session_scope
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.distribution.service import SendError, send_issue
from newsletter.slices.distribution.slack import (
    AlreadySentError,
    SlackDisabledError,
    SlackSendError,
    post_issue_to_slack,
)
from newsletter.slices.distribution.slack_client import SlackClient, SlackError
from newsletter.slices.monitoring.recorder import record_step

app = typer.Typer(
    help="Send a NewsletterIssue via SMTP.",
    no_args_is_help=True,
    add_completion=False,
)

slack_app = typer.Typer(
    help="Post an approved NewsletterIssue to Slack as a summary card.",
    no_args_is_help=True,
    add_completion=False,
)


def _build_slack_client() -> SlackClient | None:
    return SlackClient.from_settings()


@app.command()
def send(
    issue: int = typer.Option(..., "--issue", help="NewsletterIssue id."),
    dry_run: bool = typer.Option(
        False, "--dry-run/--no-dry-run", help="Simulate without contacting SMTP."
    ),
) -> None:
    """Send an approved newsletter issue."""
    with record_step("send", meta={"issue_id": issue, "dry_run": dry_run}) as run_log:
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
        run_log.item_count = len(report.recipients)

    if report.dry_run:
        typer.echo(f"[DRY-RUN] {len(report.recipients)}명에게 발송 시뮬레이션 완료.")
    else:
        typer.echo(f"발송 완료: {len(report.recipients)}명, sent_at={report.sent_at.isoformat()}")


@slack_app.command()
def slack(
    issue: int = typer.Option(..., "--issue", help="NewsletterIssue id."),
    dry_run: bool = typer.Option(
        False, "--dry-run/--no-dry-run", help="Build the card without posting."
    ),
    force: bool = typer.Option(
        False, "--force", help="Re-post even if slack_sent_at is already set."
    ),
) -> None:
    """Post an approved newsletter issue to Slack."""
    client = _build_slack_client()
    with record_step("slack", meta={"issue_id": issue, "dry_run": dry_run}) as run_log:
        with session_scope() as session:
            row = session.get(NewsletterIssue, issue)
            if row is None:
                typer.echo(f"이슈 {issue} 를 찾을 수 없습니다.", err=True)
                raise typer.Exit(code=1)
            try:
                report = post_issue_to_slack(
                    session, row, client=client, dry_run=dry_run, force=force
                )
            except (SlackDisabledError, SlackSendError, AlreadySentError) as exc:
                typer.echo(f"Slack 발송 실패: {exc}", err=True)
                raise typer.Exit(code=1) from exc
            except SlackError as exc:
                typer.echo(f"Slack 호출 실패: {exc}", err=True)
                raise typer.Exit(code=1) from exc
        run_log.item_count = 1

    if report.dry_run:
        typer.echo("[DRY-RUN] Slack 카드 미리보기 완료(미발송).")
    else:
        typer.echo(f"Slack 발송 완료: posted_at={report.posted_at.isoformat()}")
