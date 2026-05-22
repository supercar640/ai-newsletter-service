"""dashboard CLI smoke tests."""

from __future__ import annotations

from datetime import datetime

from typer.testing import CliRunner

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.dashboard.cli import app
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate

runner = CliRunner()


def _seed(db_session) -> None:
    sources_repo.add(
        db_session,
        SourceCreate(
            source_id="src",
            name="My Source",
            type="RSS",
            content_track="expert_news",  # type: ignore[arg-type]
            endpoint="https://example.com",
            category="AI Model",
            trust_level="media",  # type: ignore[arg-type]
        ),
    )
    raw = RawItem(
        source_id="src",
        title="headline",
        url="https://example.com/x",
        published_at=datetime(2026, 5, 20, 9, 0),
        collected_at=datetime(2026, 5, 20, 9, 0),
        raw_summary="news",
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(
        ProcessedItem(
            raw_item_id=raw.id,
            normalized_title="headline",
            canonical_url="https://example.com/x",
            content_track="expert_news",
            category="AI Model",
            relevance_score=0.9,
            importance_score=1.0,
            summary="news",
        )
    )
    db_session.commit()


def test_dashboard_smoke(db_session):
    _seed(db_session)
    result = runner.invoke(app, ["--since", "2026-05-15", "--until", "2026-05-22"])
    assert result.exit_code == 0, result.output
    assert "성과 대시보드" in result.output
    assert "My Source" in result.output


def test_dashboard_html_format(db_session):
    _seed(db_session)
    result = runner.invoke(
        app, ["--since", "2026-05-15", "--until", "2026-05-22", "--format", "html"]
    )
    assert result.exit_code == 0, result.output
    assert result.output.lstrip().startswith("<!DOCTYPE html>")
    assert "성과 대시보드" in result.output


def test_dashboard_save_to_file(tmp_path, db_session):
    _seed(db_session)
    out = tmp_path / "dash.md"
    result = runner.invoke(
        app, ["--since", "2026-05-15", "--until", "2026-05-22", "--save", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "성과 대시보드" in out.read_text(encoding="utf-8")


def test_dashboard_rejects_bad_format(db_session):
    result = runner.invoke(app, ["--format", "pdf"])
    assert result.exit_code != 0
