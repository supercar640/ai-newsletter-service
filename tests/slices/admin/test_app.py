"""Admin FastAPI app smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from newsletter.admin.app import create_app


def test_create_app_returns_fastapi_instance():
    app = create_app()
    assert app is not None
    assert app.title == "AI Newsletter Admin"


def test_dashboard_renders(db_session):
    app = create_app()
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_static_css_served(db_session):
    app = create_app()
    client = TestClient(app)
    response = client.get("/static/css/tokens.css")
    assert response.status_code == 200
    assert "--color-accent-primary" in response.text
