"""newsletter draft CLI — audience flag."""

from __future__ import annotations

from typer.testing import CliRunner

from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.newsletter.cli import app

runner = CliRunner()


def test_draft_default_audience_is_general(db_session, monkeypatch):
    from newsletter.slices.newsletter import cli as nl_cli

    captured = {}

    def fake_draft_issue(session, **kwargs):
        captured.update(kwargs)
        return type(
            "Rep",
            (),
            {
                "issue_id": 1,
                "issue_date": kwargs["today"],
                "audience": kwargs.get("audience", "general"),
                "expert_clusters_used": 1,
                "practical_clusters_used": 0,
                "candidate_count": 1,
            },
        )()

    monkeypatch.setattr(nl_cli, "draft_issue", fake_draft_issue)
    monkeypatch.setattr(nl_cli, "build_llm_client", lambda: object())
    result = runner.invoke(app, ["--date", "2026-05-19"])
    assert result.exit_code == 0, f"out={result.output} exc={result.exception!r}"
    assert captured["audience"] == "general"
    assert captured["expert_count"] is None
    assert captured["practical_count"] is None


def test_draft_executive_passes_audience_through(db_session, monkeypatch):
    from newsletter.slices.newsletter import cli as nl_cli

    captured = {}

    def fake_draft_issue(session, **kwargs):
        captured.update(kwargs)
        return type(
            "Rep",
            (),
            {
                "issue_id": 2,
                "issue_date": kwargs["today"],
                "audience": "executive",
                "expert_clusters_used": 3,
                "practical_clusters_used": 2,
                "candidate_count": 5,
            },
        )()

    monkeypatch.setattr(nl_cli, "draft_issue", fake_draft_issue)
    monkeypatch.setattr(nl_cli, "build_llm_client", lambda: object())
    result = runner.invoke(app, ["--date", "2026-05-19", "--audience", "executive"])
    assert result.exit_code == 0, result.stdout
    assert captured["audience"] == "executive"
    assert "executive" in result.stdout


def test_draft_rejects_unknown_audience(db_session, monkeypatch):
    from newsletter.slices.newsletter import cli as nl_cli

    monkeypatch.setattr(nl_cli, "draft_issue", lambda *a, **k: None)
    monkeypatch.setattr(nl_cli, "build_llm_client", lambda: object())
    result = runner.invoke(app, ["--audience", "intern"])
    assert result.exit_code != 0
    # Typer puts validation errors on stderr.
    assert "intern" in (result.output + (result.stderr if result.stderr_bytes else ""))


def test_draft_explicit_counts_override_audience(db_session, monkeypatch):
    from newsletter.slices.newsletter import cli as nl_cli

    captured = {}

    def fake_draft_issue(session, **kwargs):
        captured.update(kwargs)
        return type(
            "Rep",
            (),
            {
                "issue_id": 3,
                "issue_date": kwargs["today"],
                "audience": "executive",
                "expert_clusters_used": 1,
                "practical_clusters_used": 1,
                "candidate_count": 2,
            },
        )()

    monkeypatch.setattr(nl_cli, "draft_issue", fake_draft_issue)
    monkeypatch.setattr(nl_cli, "build_llm_client", lambda: object())
    result = runner.invoke(
        app,
        [
            "--date",
            "2026-05-19",
            "--audience",
            "executive",
            "--expert-count",
            "1",
            "--practical-count",
            "1",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert captured["expert_count"] == 1
    assert captured["practical_count"] == 1


# Smoke import to keep ruff happy: NewsletterIssue is referenced from the
# integration test path elsewhere; not used in the per-CLI test above.
_ = NewsletterIssue
