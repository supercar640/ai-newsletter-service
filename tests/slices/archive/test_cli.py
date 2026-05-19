"""archive CLI — issue / backfill commands."""

from __future__ import annotations

from datetime import date

from typer.testing import CliRunner

from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.archive import cli as archive_cli
from newsletter.slices.archive.cli import app

runner = CliRunner()


class _FakeNotion:
    def __init__(self):
        self.calls = 0
        self.database_id = "db-1"

    def create_page(self, **kwargs):
        self.calls += 1
        return f"page-{self.calls}"


def _seed_sent(db_session, **overrides) -> NewsletterIssue:
    issue = NewsletterIssue(
        issue_date=date(2026, 5, 19),
        title="hello",
        status="sent",
        audience="general",
        markdown_body="# title\nbody",
    )
    for k, v in overrides.items():
        setattr(issue, k, v)
    db_session.add(issue)
    db_session.commit()
    db_session.refresh(issue)
    return issue


def test_issue_command_archives(db_session, monkeypatch):
    issue = _seed_sent(db_session)
    monkeypatch.setattr(archive_cli, "_build_client", lambda: _FakeNotion())
    result = runner.invoke(app, ["issue", str(issue.id)])
    assert result.exit_code == 0, result.output
    db_session.expire_all()
    refreshed = db_session.get(NewsletterIssue, issue.id)
    assert refreshed.notion_page_id == "page-1"


def test_issue_command_when_disabled_exits_nonzero(db_session, monkeypatch):
    issue = _seed_sent(db_session)
    monkeypatch.setattr(archive_cli, "_build_client", lambda: None)
    result = runner.invoke(app, ["issue", str(issue.id)])
    assert result.exit_code != 0


def test_issue_command_unknown_id(db_session, monkeypatch):
    monkeypatch.setattr(archive_cli, "_build_client", lambda: _FakeNotion())
    result = runner.invoke(app, ["issue", "999"])
    assert result.exit_code != 0


def test_issue_force_overwrites_existing_page_id(db_session, monkeypatch):
    issue = _seed_sent(db_session, notion_page_id="old-page")
    monkeypatch.setattr(archive_cli, "_build_client", lambda: _FakeNotion())
    # Without --force, refuses.
    refuse = runner.invoke(app, ["issue", str(issue.id)])
    assert refuse.exit_code != 0
    # With --force, replaces.
    ok = runner.invoke(app, ["issue", str(issue.id), "--force"])
    assert ok.exit_code == 0, ok.output
    db_session.expire_all()
    refreshed = db_session.get(NewsletterIssue, issue.id)
    assert refreshed.notion_page_id == "page-1"


def test_backfill_archives_pending_sent_issues(db_session, monkeypatch):
    a = _seed_sent(db_session)
    b = _seed_sent(db_session)
    _seed_sent(db_session, notion_page_id="already")
    monkeypatch.setattr(archive_cli, "_build_client", lambda: _FakeNotion())
    result = runner.invoke(app, ["backfill"])
    assert result.exit_code == 0, result.output
    assert "신규=2" in result.output
    assert "스킵=1" in result.output
    db_session.expire_all()
    assert db_session.get(NewsletterIssue, a.id).notion_page_id is not None
    assert db_session.get(NewsletterIssue, b.id).notion_page_id is not None
