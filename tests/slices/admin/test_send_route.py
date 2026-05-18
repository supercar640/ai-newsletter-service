"""Send-confirm + send-action route tests, including the approved gate."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from newsletter.admin.app import create_app
from newsletter.admin.deps import get_db
from newsletter.core.config import get_settings


def _client(db_session) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def _send_settings(monkeypatch: pytest.MonkeyPatch, db_session):
    # Depending on db_session forces ordering: the outer `settings` fixture
    # blanks credential env vars to insulate tests from a real .env, so we
    # repopulate the ones this route needs *after* that runs.
    _ = db_session
    monkeypatch.setenv("NEWSLETTER_RECIPIENTS", "ops@example.com,dev@example.com")
    monkeypatch.setenv("SMTP_FROM", "newsletter@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_send_confirm_renders_recipients(db_session, make_issue):
    issue = make_issue(status="approved", title="Confirmable")
    db_session.commit()
    res = _client(db_session).get(f"/issues/{issue.id}/send")
    assert res.status_code == 200
    assert "Confirmable" in res.text
    assert "ops@example.com" in res.text
    assert "dev@example.com" in res.text


def test_send_confirm_warns_when_not_approved(db_session, make_issue):
    issue = make_issue(status="review_required")
    db_session.commit()
    res = _client(db_session).get(f"/issues/{issue.id}/send")
    assert res.status_code == 200
    assert "발송 불가" in res.text
    # The submit button should be disabled.
    assert "disabled" in res.text


def test_send_confirm_404_for_missing_issue(db_session):
    res = _client(db_session).get("/issues/9999/send")
    assert res.status_code == 404


def test_send_dry_run_redirects(db_session, make_issue):
    issue = make_issue(status="approved")
    db_session.commit()
    res = _client(db_session).post(f"/issues/{issue.id}/send", data={"dry_run": 1})
    assert res.status_code == 303
    assert res.headers["location"].startswith(f"/issues/{issue.id}")
    db_session.expire_all()
    # Dry-run must NOT mutate state.
    assert issue.status == "approved"


def test_send_real_routes_to_distribution(db_session, make_issue, monkeypatch):
    """Non-dry-run path delegates to distribution.send_issue."""
    from datetime import UTC, datetime

    from newsletter.slices.distribution.service import SendReport

    calls: list[bool] = []

    def fake_send_issue(session, issue, *, dry_run, **_kwargs):
        _ = session  # signature parity with real send_issue
        calls.append(dry_run)
        if not dry_run:
            issue.status = "sent"
        return SendReport(
            dry_run=dry_run,
            recipients=("a@example.com",),
            sent_at=None if dry_run else datetime.now(UTC),
        )

    monkeypatch.setattr("newsletter.admin.routes.send.send_issue", fake_send_issue)

    issue = make_issue(status="approved")
    db_session.commit()
    res = _client(db_session).post(f"/issues/{issue.id}/send", data={"dry_run": 0})
    assert res.status_code == 303
    assert res.headers["location"].endswith("sent=ok")
    assert calls == [False]
    db_session.expire_all()
    assert issue.status == "sent"


def test_send_rejects_when_not_approved(db_session, make_issue):
    for bad in ("drafted", "review_required", "rejected", "sent"):
        issue = make_issue(status=bad)
        db_session.commit()
        res = _client(db_session).post(f"/issues/{issue.id}/send", data={"dry_run": 1})
        assert res.status_code == 409, f"{bad} should not be sendable"


def test_send_404_for_missing_issue(db_session):
    res = _client(db_session).post("/issues/9999/send", data={"dry_run": 1})
    assert res.status_code == 404
