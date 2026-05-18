"""Issue action POST route tests — toggle / approve / reject + state gate."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from newsletter.admin.app import create_app
from newsletter.admin.deps import get_db


def _client(db_session) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    # Follow_redirects defaults to True for httpx; we want to inspect the 303.
    return TestClient(app, follow_redirects=False)


def test_toggle_redirects_back_to_review(db_session, make_issue):
    issue = make_issue(expert_entries=[(1, True)])
    db_session.commit()
    res = _client(db_session).post(
        f"/issues/{issue.id}/toggle",
        data={"track": "expert", "processed_item_id": 1, "included": 0},
    )
    assert res.status_code == 303
    assert res.headers["location"] == f"/issues/{issue.id}"


def test_toggle_persists_change(db_session, make_issue):
    issue = make_issue(expert_entries=[(7, True)])
    db_session.commit()
    _client(db_session).post(
        f"/issues/{issue.id}/toggle",
        data={"track": "expert", "processed_item_id": 7, "included": 0},
    )
    db_session.expire_all()
    blob = json.loads(issue.candidate_ids_json)
    assert blob["expert"] == [{"id": 7, "included": False}]


def test_toggle_rejects_when_approved(db_session, make_issue):
    issue = make_issue(status="approved", expert_entries=[(1, True)])
    db_session.commit()
    res = _client(db_session).post(
        f"/issues/{issue.id}/toggle",
        data={"track": "expert", "processed_item_id": 1, "included": 0},
    )
    assert res.status_code == 409


def test_approve_sets_status_to_approved(db_session, make_issue):
    issue = make_issue(status="review_required")
    db_session.commit()
    res = _client(db_session).post(
        f"/issues/{issue.id}/approve",
        data={"approved_by": "master"},
    )
    assert res.status_code == 303
    db_session.expire_all()
    assert issue.status == "approved"
    assert issue.approved_by == "master"


def test_approve_rejected_when_already_sent(db_session, make_issue):
    issue = make_issue(status="sent")
    db_session.commit()
    res = _client(db_session).post(f"/issues/{issue.id}/approve", data={"approved_by": "master"})
    assert res.status_code == 409


def test_reject_sets_status_to_rejected(db_session, make_issue):
    issue = make_issue(status="review_required")
    db_session.commit()
    res = _client(db_session).post(f"/issues/{issue.id}/reject")
    assert res.status_code == 303
    db_session.expire_all()
    assert issue.status == "rejected"


def test_reject_blocked_when_sent(db_session, make_issue):
    issue = make_issue(status="sent")
    db_session.commit()
    res = _client(db_session).post(f"/issues/{issue.id}/reject")
    assert res.status_code == 409


def test_action_routes_404_for_missing_issue(db_session):
    client = _client(db_session)
    assert client.post("/issues/9999/approve", data={"approved_by": "x"}).status_code == 404
    assert client.post("/issues/9999/reject").status_code == 404
    assert (
        client.post(
            "/issues/9999/toggle",
            data={"track": "expert", "processed_item_id": 1, "included": 1},
        ).status_code
        == 404
    )
