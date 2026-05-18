"""Dashboard route integration tests with real DB session override."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from newsletter.admin.app import create_app
from newsletter.admin.deps import get_db
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.models.raw_item import RawItem
from newsletter.models.source import Source


def _client(db_session) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_dashboard_renders_recent_issue_title(db_session):
    db_session.add(
        NewsletterIssue(
            issue_date=date(2026, 5, 18),
            title="2026-05-18 AI 인텔리전스 다이제스트",
            status="review_required",
        )
    )
    db_session.commit()

    res = _client(db_session).get("/")
    assert res.status_code == 200
    assert "2026-05-18 AI 인텔리전스 다이제스트" in res.text


def test_dashboard_renders_empty_state_when_no_issues(db_session):
    res = _client(db_session).get("/")
    assert res.status_code == 200
    assert "아직 발행된 이슈가 없습니다" in res.text


def test_dashboard_shows_review_pending_badge(db_session):
    db_session.add_all(
        [
            NewsletterIssue(issue_date=date(2026, 5, 18), title="r", status="review_required"),
            NewsletterIssue(issue_date=date(2026, 5, 17), title="a", status="approved"),
        ]
    )
    db_session.commit()
    res = _client(db_session).get("/")
    assert "검수 대기" in res.text
    assert "승인" in res.text


def test_dashboard_renders_collected_count(db_session):
    src = Source(
        source_id="src1",
        name="Test",
        type="RSS",
        content_track="expert_news",
        endpoint="http://example.com/feed",
        priority="medium",
        trust_level="media",
        fetch_interval="daily",
    )
    db_session.add(src)
    db_session.flush()
    db_session.add(
        RawItem(
            source_id=src.source_id,
            title="hi",
            url="http://example.com/a",
            collected_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    res = _client(db_session).get("/")
    assert res.status_code == 200
