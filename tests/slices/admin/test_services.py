"""State-machine + toggle behavior for write-side issue services."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from newsletter.admin.services import (
    IssueStateError,
    approve_issue,
    reject_issue,
    toggle_candidate,
)


def test_toggle_candidate_persists_included_flag(db_session, make_issue):
    issue = make_issue(expert_entries=[(1, True), (2, True)])
    db_session.commit()

    toggle_candidate(db_session, issue, track="expert", processed_item_id=2, included=False)
    db_session.commit()
    db_session.refresh(issue)

    blob = json.loads(issue.candidate_ids_json)
    assert blob["expert"] == [
        {"id": 1, "included": True},
        {"id": 2, "included": False},
    ]


def test_toggle_candidate_adds_entry_if_missing(db_session, make_issue):
    issue = make_issue(expert_entries=[])
    db_session.commit()

    toggle_candidate(db_session, issue, track="expert", processed_item_id=42, included=True)
    db_session.commit()

    blob = json.loads(issue.candidate_ids_json)
    assert blob["expert"] == [{"id": 42, "included": True}]


def test_toggle_candidate_rejects_unknown_track(db_session, make_issue):
    issue = make_issue()
    db_session.commit()
    with pytest.raises(IssueStateError):
        toggle_candidate(db_session, issue, track="bogus", processed_item_id=1, included=True)


def test_toggle_candidate_blocked_when_approved(db_session, make_issue):
    issue = make_issue(status="approved")
    db_session.commit()
    with pytest.raises(IssueStateError):
        toggle_candidate(db_session, issue, track="expert", processed_item_id=1, included=False)


def test_toggle_candidate_blocked_when_sent(db_session, make_issue):
    issue = make_issue(status="sent")
    db_session.commit()
    with pytest.raises(IssueStateError):
        toggle_candidate(db_session, issue, track="expert", processed_item_id=1, included=False)


def test_approve_issue_transitions_to_approved(db_session, make_issue):
    issue = make_issue(status="review_required")
    db_session.commit()

    now = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
    approve_issue(db_session, issue, approved_by="master", now=now)
    db_session.commit()
    db_session.refresh(issue)

    assert issue.status == "approved"
    assert issue.approved_by == "master"
    # SQLite strips tzinfo on round-trip; re-attach UTC for comparison.
    assert issue.approved_at is not None
    assert issue.approved_at.replace(tzinfo=UTC) == now


def test_approve_issue_works_from_drafted(db_session, make_issue):
    issue = make_issue(status="drafted")
    db_session.commit()
    approve_issue(db_session, issue, approved_by="master")
    assert issue.status == "approved"


def test_approve_issue_blocked_when_already_sent(db_session, make_issue):
    issue = make_issue(status="sent")
    db_session.commit()
    with pytest.raises(IssueStateError):
        approve_issue(db_session, issue, approved_by="master")


def test_approve_issue_blocked_when_rejected(db_session, make_issue):
    issue = make_issue(status="rejected")
    db_session.commit()
    with pytest.raises(IssueStateError):
        approve_issue(db_session, issue, approved_by="master")


def test_reject_issue_sets_rejected_and_clears_approval(db_session, make_issue):
    issue = make_issue(status="review_required")
    issue.approved_by = "previous"
    issue.approved_at = datetime(2026, 5, 18, tzinfo=UTC)
    db_session.commit()

    reject_issue(db_session, issue)
    db_session.commit()
    db_session.refresh(issue)
    assert issue.status == "rejected"
    assert issue.approved_by is None
    assert issue.approved_at is None


def test_reject_issue_blocked_when_sent(db_session, make_issue):
    issue = make_issue(status="sent")
    db_session.commit()
    with pytest.raises(IssueStateError):
        reject_issue(db_session, issue)
