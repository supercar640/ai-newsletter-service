"""Tests for get_issue_detail / list_issues."""

from __future__ import annotations

from datetime import date

from newsletter.admin.data import get_issue_detail, list_issues


def test_get_issue_detail_returns_none_for_missing(db_session):
    assert get_issue_detail(db_session, 99999) is None


def test_get_issue_detail_resolves_candidates(db_session, make_processed_item, make_issue):
    a = make_processed_item(title="A item", importance=0.9, category="LLM")
    b = make_processed_item(title="B item", importance=0.5, category="Robotics")
    c = make_processed_item(title="C item", track="practical_insight", importance=0.7)
    db_session.commit()

    issue = make_issue(
        expert_entries=[(a.id, True), (b.id, False)],
        practical_entries=[(c.id, True)],
    )
    db_session.commit()

    detail = get_issue_detail(db_session, issue.id)
    assert detail is not None
    assert detail.issue.id == issue.id
    assert [c.title for c in detail.expert_candidates] == ["A item", "B item"]
    assert detail.expert_candidates[0].included is True
    assert detail.expert_candidates[0].category == "LLM"
    assert detail.expert_candidates[0].importance_score == 0.9
    assert detail.expert_candidates[1].included is False
    assert [c.title for c in detail.practical_candidates] == ["C item"]
    assert detail.practical_candidates[0].track == "practical"


def test_get_issue_detail_skips_missing_processed_items(db_session, make_issue):
    issue = make_issue(expert_entries=[(99999, True)])
    db_session.commit()

    detail = get_issue_detail(db_session, issue.id)
    assert detail is not None
    assert detail.expert_candidates == []


def test_get_issue_detail_handles_legacy_int_list(db_session, make_processed_item, make_issue):
    a = make_processed_item(title="A")
    issue = make_issue()  # no candidate blob yet
    issue.candidate_ids_json = f'{{"expert": [{a.id}], "practical": []}}'
    db_session.commit()

    detail = get_issue_detail(db_session, issue.id)
    assert detail is not None
    assert len(detail.expert_candidates) == 1
    assert detail.expert_candidates[0].included is True


def test_list_issues_filters_by_status(db_session, make_issue):
    make_issue(issue_date_=date(2026, 5, 17), status="approved", title="approved one")
    make_issue(issue_date_=date(2026, 5, 18), status="review_required", title="pending")
    make_issue(issue_date_=date(2026, 5, 16), status="sent", title="sent one")
    db_session.commit()

    pending = list_issues(db_session, status="review_required")
    assert [r.title for r in pending] == ["pending"]


def test_list_issues_orders_newest_first(db_session, make_issue):
    make_issue(issue_date_=date(2026, 5, 17), title="r17")
    make_issue(issue_date_=date(2026, 5, 18), title="r18")
    db_session.commit()

    rows = list_issues(db_session)
    assert [r.title for r in rows] == ["r18", "r17"]
