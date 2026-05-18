"""Tests for admin/data.py — dashboard read helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime

from newsletter.admin.data import get_dashboard_stats, list_recent_issues
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.models.source import Source

TODAY = date(2026, 5, 18)


def _make_source(session, source_id: str = "src1") -> Source:
    s = Source(
        source_id=source_id,
        name="Test Source",
        type="RSS",
        content_track="expert_news",
        endpoint="http://example.com/feed",
        priority="medium",
        trust_level="media",
        fetch_interval="daily",
    )
    session.add(s)
    session.flush()
    return s


def test_empty_db_returns_zero_counts(db_session):
    stats = get_dashboard_stats(db_session, TODAY)
    assert stats.collected_today == 0
    assert stats.processed_today == 0
    assert stats.candidates_count == 0
    assert stats.pending_review == 0


def test_stats_counts_today_only(db_session):
    src = _make_source(db_session)
    today_raw = RawItem(
        source_id=src.source_id,
        title="today",
        url="http://example.com/today",
        collected_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
    )
    yesterday_raw = RawItem(
        source_id=src.source_id,
        title="yesterday",
        url="http://example.com/yesterday",
        collected_at=datetime(2026, 5, 17, 10, 0, tzinfo=UTC),
    )
    db_session.add_all([today_raw, yesterday_raw])
    db_session.flush()

    db_session.add_all(
        [
            ProcessedItem(
                raw_item_id=today_raw.id,
                normalized_title="today",
                canonical_url="http://example.com/today",
                content_track="expert_news",
                created_at=datetime(2026, 5, 18, 11, 0, tzinfo=UTC),
            ),
            ProcessedItem(
                raw_item_id=yesterday_raw.id,
                normalized_title="yesterday",
                canonical_url="http://example.com/yesterday",
                content_track="expert_news",
                created_at=datetime(2026, 5, 17, 11, 0, tzinfo=UTC),
            ),
        ]
    )
    db_session.commit()

    stats = get_dashboard_stats(db_session, TODAY)
    assert stats.collected_today == 1
    assert stats.processed_today == 1


def test_pending_review_counts_only_review_required(db_session):
    db_session.add_all(
        [
            NewsletterIssue(issue_date=date(2026, 5, 17), title="r", status="review_required"),
            NewsletterIssue(issue_date=date(2026, 5, 16), title="a", status="approved"),
            NewsletterIssue(issue_date=date(2026, 5, 15), title="d", status="drafted"),
        ]
    )
    db_session.commit()

    stats = get_dashboard_stats(db_session, TODAY)
    assert stats.pending_review == 1


def test_candidates_count_from_today_issue(db_session):
    db_session.add(
        NewsletterIssue(
            issue_date=TODAY,
            title="today issue",
            status="review_required",
            candidate_ids_json='{"expert": [1, 2, 3], "practical": [4, 5]}',
        )
    )
    db_session.commit()

    stats = get_dashboard_stats(db_session, TODAY)
    assert stats.candidates_count == 5


def test_list_recent_issues_returns_newest_first(db_session):
    db_session.add_all(
        [
            NewsletterIssue(issue_date=date(2026, 5, 17), title="r17", status="drafted"),
            NewsletterIssue(issue_date=date(2026, 5, 18), title="r18", status="approved"),
            NewsletterIssue(issue_date=date(2026, 5, 16), title="r16", status="sent"),
        ]
    )
    db_session.commit()

    recent = list_recent_issues(db_session, limit=10)
    assert [r.issue_date for r in recent] == [
        date(2026, 5, 18),
        date(2026, 5, 17),
        date(2026, 5, 16),
    ]
    assert recent[0].title == "r18"


def test_list_recent_issues_includes_candidate_counts(db_session):
    db_session.add(
        NewsletterIssue(
            issue_date=TODAY,
            title="counted",
            status="review_required",
            candidate_ids_json='{"expert": [1, 2, 3], "practical": [4, 5]}',
        )
    )
    db_session.commit()

    recent = list_recent_issues(db_session)
    assert recent[0].expert_count == 3
    assert recent[0].practical_count == 2
