"""send_issue tests — state machine + dry-run + recipient guard."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import pytest

from newsletter.core.config import get_settings
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.distribution.sender import Mail
from newsletter.slices.distribution.service import SendError, send_issue


@dataclass
class _StubSender:
    sent: list[Mail] = field(default_factory=list)
    raise_on_send: Exception | None = None

    def send(self, mail: Mail) -> None:
        if self.raise_on_send is not None:
            raise self.raise_on_send
        self.sent.append(mail)


@pytest.fixture
def smtp_env(monkeypatch: pytest.MonkeyPatch, db_session):
    # Order: db_session first (which blanks credential env), then us.
    _ = db_session
    monkeypatch.setenv("NEWSLETTER_RECIPIENTS", "alice@example.com,bob@example.com")
    monkeypatch.setenv("SMTP_FROM", "newsletter@example.com")
    monkeypatch.setenv("SMTP_USER", "newsletter@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_approved_issue(db_session) -> NewsletterIssue:
    issue = NewsletterIssue(
        issue_date=date(2026, 5, 19),
        title="[AI 뉴스레터] 2026-05-19",
        status="approved",
        markdown_body="# Title\n\nBody.",
        html_body="<h1>Title</h1><p>Body.</p>",
    )
    db_session.add(issue)
    db_session.flush()
    return issue


def test_send_issue_dry_run_does_not_mutate(db_session, smtp_env):
    issue = _make_approved_issue(db_session)
    db_session.commit()
    sender = _StubSender()

    report = send_issue(db_session, issue, sender=sender, dry_run=True)
    db_session.commit()
    db_session.refresh(issue)

    assert report.dry_run is True
    assert report.sent_at is None
    assert report.recipients == ("alice@example.com", "bob@example.com")
    assert sender.sent == []
    assert issue.status == "approved"
    assert issue.sent_at is None


def test_send_issue_real_send_records_sent_status(db_session, smtp_env):
    issue = _make_approved_issue(db_session)
    db_session.commit()
    sender = _StubSender()
    now = datetime(2026, 5, 19, 9, 0, tzinfo=UTC)

    report = send_issue(db_session, issue, sender=sender, dry_run=False, now=now)
    db_session.commit()
    db_session.refresh(issue)

    assert report.dry_run is False
    assert report.sent_at == now
    assert len(sender.sent) == 1
    mail = sender.sent[0]
    assert mail.subject == "[AI 뉴스레터] 2026-05-19"
    assert mail.recipients == ("alice@example.com", "bob@example.com")
    assert mail.sender == "newsletter@example.com"
    assert "<h1>Title</h1>" in (mail.html_body or "")
    # Markdown stripped in plain alternative
    assert mail.plain_body.startswith("Title")

    assert issue.status == "sent"
    assert issue.sent_at is not None
    assert issue.sent_at.replace(tzinfo=UTC) == now


@pytest.mark.parametrize(
    "bad_status",
    ["drafted", "review_required", "rejected", "sent"],
)
def test_send_issue_rejects_non_approved(db_session, smtp_env, bad_status):
    issue = NewsletterIssue(
        issue_date=date(2026, 5, 19),
        title="title",
        status=bad_status,
        markdown_body="x",
        html_body="<p>x</p>",
    )
    db_session.add(issue)
    db_session.commit()
    sender = _StubSender()
    with pytest.raises(SendError):
        send_issue(db_session, issue, sender=sender, dry_run=False)
    assert sender.sent == []


def test_send_issue_rejects_when_recipients_empty(db_session, smtp_env, monkeypatch):
    monkeypatch.setenv("NEWSLETTER_RECIPIENTS", "")
    get_settings.cache_clear()
    issue = _make_approved_issue(db_session)
    db_session.commit()
    sender = _StubSender()
    with pytest.raises(SendError):
        send_issue(db_session, issue, sender=sender, dry_run=True)


def test_send_issue_rejects_when_sender_address_missing(db_session, smtp_env, monkeypatch):
    monkeypatch.setenv("SMTP_FROM", "")
    monkeypatch.setenv("SMTP_USER", "")
    get_settings.cache_clear()
    issue = _make_approved_issue(db_session)
    db_session.commit()
    sender = _StubSender()
    with pytest.raises(SendError):
        send_issue(db_session, issue, sender=sender, dry_run=True)
