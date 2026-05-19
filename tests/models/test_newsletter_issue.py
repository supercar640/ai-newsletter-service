"""NewsletterIssue model tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from newsletter.models.newsletter_issue import NewsletterIssue


def test_minimal_insert_defaults_status_to_drafted(db_session):
    issue = NewsletterIssue(
        issue_date=date(2026, 5, 18),
        title="2026-05-18 AI 인텔리전스 다이제스트",
    )
    db_session.add(issue)
    db_session.commit()
    db_session.refresh(issue)
    assert issue.id is not None
    assert issue.status == "drafted"
    assert issue.created_at is not None
    assert issue.approved_at is None
    assert issue.sent_at is None


def test_status_check_constraint_rejects_unknown_values(db_session):
    issue = NewsletterIssue(
        issue_date=date(2026, 5, 18),
        title="bogus",
        status="not-a-real-status",
    )
    db_session.add(issue)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_audience_default_null(db_session):
    issue = NewsletterIssue(
        issue_date=date(2026, 5, 19),
        title="no audience",
    )
    db_session.add(issue)
    db_session.commit()
    db_session.refresh(issue)
    assert issue.audience is None


def test_audience_accepts_known_values(db_session):
    for value in ("general", "executive", "technical"):
        issue = NewsletterIssue(
            issue_date=date(2026, 5, 19),
            title=f"v={value}",
            audience=value,
        )
        db_session.add(issue)
    db_session.commit()


def test_audience_rejects_unknown(db_session):
    issue = NewsletterIssue(
        issue_date=date(2026, 5, 19),
        title="bad",
        audience="intern",
    )
    db_session.add(issue)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_full_lifecycle_fields_persist(db_session):
    issue = NewsletterIssue(
        issue_date=date(2026, 5, 18),
        title="lifecycle",
        status="approved",
        expert_section_md="# expert",
        practical_section_md="# practical",
        markdown_body="# combined",
        html_body="<h1>combined</h1>",
        candidate_ids_json='{"expert": [1, 2], "practical": [3]}',
        approved_by="master",
        approved_at=datetime(2026, 5, 18, 9, 0, tzinfo=UTC),
    )
    db_session.add(issue)
    db_session.commit()
    db_session.refresh(issue)
    assert issue.expert_section_md == "# expert"
    assert issue.practical_section_md == "# practical"
    assert issue.candidate_ids_json == '{"expert": [1, 2], "practical": [3]}'
    assert issue.approved_by == "master"
    assert issue.approved_at is not None
