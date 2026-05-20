"""slack CLI — `newsletter slack --issue ID [--dry-run] [--force]`."""

from __future__ import annotations

from datetime import UTC, date, datetime

from typer.testing import CliRunner

from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.distribution import cli as dist_cli
from newsletter.slices.distribution.cli import slack_app

runner = CliRunner()


class _FakeSlack:
    def __init__(self):
        self.posts = 0

    def post(self, blocks):
        self.posts += 1


def _seed(db_session, **overrides) -> NewsletterIssue:
    issue = NewsletterIssue(
        issue_date=date(2026, 5, 20),
        title="hello",
        status="approved",
        audience="general",
        markdown_body="## A\n\n#### 뉴스 1. 헤드라인\n- 요약: x\n",
    )
    for k, v in overrides.items():
        setattr(issue, k, v)
    db_session.add(issue)
    db_session.commit()
    db_session.refresh(issue)
    return issue


def test_slack_command_posts(db_session, monkeypatch):
    issue = _seed(db_session)
    monkeypatch.setattr(dist_cli, "_build_slack_client", lambda: _FakeSlack())
    result = runner.invoke(slack_app, ["--issue", str(issue.id)])
    assert result.exit_code == 0, result.output
    db_session.expire_all()
    assert db_session.get(NewsletterIssue, issue.id).slack_sent_at is not None


def test_slack_command_dry_run_does_not_record(db_session, monkeypatch):
    issue = _seed(db_session)
    monkeypatch.setattr(dist_cli, "_build_slack_client", lambda: _FakeSlack())
    result = runner.invoke(slack_app, ["--issue", str(issue.id), "--dry-run"])
    assert result.exit_code == 0, result.output
    db_session.expire_all()
    assert db_session.get(NewsletterIssue, issue.id).slack_sent_at is None


def test_slack_command_refuses_unapproved(db_session, monkeypatch):
    issue = _seed(db_session, status="review_required")
    monkeypatch.setattr(dist_cli, "_build_slack_client", lambda: _FakeSlack())
    result = runner.invoke(slack_app, ["--issue", str(issue.id)])
    assert result.exit_code != 0


def test_slack_command_when_disabled_exits_nonzero(db_session, monkeypatch):
    issue = _seed(db_session)
    monkeypatch.setattr(dist_cli, "_build_slack_client", lambda: None)
    result = runner.invoke(slack_app, ["--issue", str(issue.id)])
    assert result.exit_code != 0


def test_slack_command_unknown_id(db_session, monkeypatch):
    monkeypatch.setattr(dist_cli, "_build_slack_client", lambda: _FakeSlack())
    result = runner.invoke(slack_app, ["--issue", "999"])
    assert result.exit_code != 0


def test_slack_command_force_reposts(db_session, monkeypatch):
    issue = _seed(db_session, slack_sent_at=datetime(2026, 5, 20, 1, tzinfo=UTC))
    monkeypatch.setattr(dist_cli, "_build_slack_client", lambda: _FakeSlack())
    refuse = runner.invoke(slack_app, ["--issue", str(issue.id)])
    assert refuse.exit_code != 0
    ok = runner.invoke(slack_app, ["--issue", str(issue.id), "--force"])
    assert ok.exit_code == 0, ok.output
