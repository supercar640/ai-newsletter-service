"""Issue list + review route tests (read-only)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from newsletter.admin.app import create_app
from newsletter.admin.deps import get_db


def _client(db_session) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_issue_list_renders_empty_state(db_session):
    res = _client(db_session).get("/issues")
    assert res.status_code == 200
    assert "검수할 이슈가 없습니다" in res.text


def test_issue_list_renders_issue_rows(db_session, make_issue):
    make_issue(title="2026-05-18 다이제스트")
    db_session.commit()
    res = _client(db_session).get("/issues")
    assert res.status_code == 200
    assert "2026-05-18 다이제스트" in res.text


def test_issue_review_returns_404_for_missing_id(db_session):
    res = _client(db_session).get("/issues/99999")
    assert res.status_code == 404


def test_issue_review_renders_candidate_titles(db_session, make_processed_item, make_issue):
    a = make_processed_item(title="Llama 4 출시", importance=0.92)
    b = make_processed_item(title="Anthropic 신모델 발표", importance=0.81)
    c = make_processed_item(title="실무 프롬프트 팁", track="practical_insight", importance=0.7)
    db_session.commit()

    issue = make_issue(
        expert_entries=[(a.id, True), (b.id, False)],
        practical_entries=[(c.id, True)],
        expert_section_md="# 전문가 트랙\n\n**중요한 내용입니다.**",
        practical_section_md="# 일반\n\n간단한 안내.",
    )
    db_session.commit()

    res = _client(db_session).get(f"/issues/{issue.id}")
    assert res.status_code == 200
    assert "Llama 4 출시" in res.text
    assert "Anthropic 신모델 발표" in res.text
    assert "실무 프롬프트 팁" in res.text
    # Markdown rendered to HTML
    assert "<strong>중요한 내용입니다.</strong>" in res.text
    # Importance scores rendered with 2-decimal format
    assert "0.92" in res.text
    # Excluded candidate gets the excluded class
    assert "candidate-row--excluded" in res.text


def test_issue_review_shows_empty_states_when_no_drafts(db_session, make_issue):
    issue = make_issue(expert_section_md=None, practical_section_md=None)
    db_session.commit()
    res = _client(db_session).get(f"/issues/{issue.id}")
    assert res.status_code == 200
    assert "초안이 아직 생성되지 않았습니다" in res.text
