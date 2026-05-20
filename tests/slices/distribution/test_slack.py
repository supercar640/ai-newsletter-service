"""distribution.slack — post_issue_to_slack (approved guard + idempotency)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.distribution.slack import (
    AlreadySentError,
    SlackDisabledError,
    SlackSendError,
    post_issue_to_slack,
)


class _FakeSlack:
    def __init__(self) -> None:
        self.posts: list[list[dict]] = []

    def post(self, blocks: list[dict]) -> None:
        self.posts.append(blocks)


def _make_issue(
    db_session,
    *,
    status: str = "approved",
    slack_sent_at: datetime | None = None,
    title: str = "오늘의 AI",
    markdown_body: str = "## A\n\n#### 뉴스 1. 헤드라인\n- 요약: x\n",
) -> NewsletterIssue:
    issue = NewsletterIssue(
        issue_date=date(2026, 5, 20),
        title=title,
        status=status,
        audience="general",
        markdown_body=markdown_body,
        slack_sent_at=slack_sent_at,
    )
    db_session.add(issue)
    db_session.commit()
    db_session.refresh(issue)
    return issue


def test_posts_card_and_records_timestamp(db_session):
    issue = _make_issue(db_session)
    client = _FakeSlack()
    report = post_issue_to_slack(db_session, issue, client=client)
    db_session.commit()
    db_session.refresh(issue)
    assert len(client.posts) == 1
    assert issue.slack_sent_at is not None
    assert report.dry_run is False


def test_refuses_when_not_approved(db_session):
    issue = _make_issue(db_session, status="review_required")
    client = _FakeSlack()
    with pytest.raises(SlackSendError):
        post_issue_to_slack(db_session, issue, client=client)
    assert client.posts == []


def test_refuses_when_client_missing(db_session):
    issue = _make_issue(db_session)
    with pytest.raises(SlackDisabledError):
        post_issue_to_slack(db_session, issue, client=None)


def test_idempotent_unless_forced(db_session):
    issue = _make_issue(db_session, slack_sent_at=datetime(2026, 5, 20, 1, tzinfo=UTC))
    client = _FakeSlack()
    with pytest.raises(AlreadySentError):
        post_issue_to_slack(db_session, issue, client=client)
    assert client.posts == []


def test_force_reposts_already_sent(db_session):
    issue = _make_issue(db_session, slack_sent_at=datetime(2026, 5, 20, 1, tzinfo=UTC))
    client = _FakeSlack()
    post_issue_to_slack(db_session, issue, client=client, force=True)
    assert len(client.posts) == 1


def test_dry_run_does_not_post_or_record(db_session):
    issue = _make_issue(db_session)
    client = _FakeSlack()
    report = post_issue_to_slack(db_session, issue, client=client, dry_run=True)
    db_session.commit()
    db_session.refresh(issue)
    assert client.posts == []
    assert issue.slack_sent_at is None
    assert report.dry_run is True
