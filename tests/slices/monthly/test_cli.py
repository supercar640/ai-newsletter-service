"""monthly CLI smoke tests. ANTHROPIC_API_KEY is blank in tests, so the
narrative is skipped automatically — output is deterministic."""

from __future__ import annotations

from datetime import datetime

from typer.testing import CliRunner

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.monthly.cli import app
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate

runner = CliRunner()


def _seed(db_session) -> None:
    sources_repo.add(
        db_session,
        SourceCreate(
            source_id="src",
            name="src",
            type="RSS",
            content_track="expert_news",  # type: ignore[arg-type]
            endpoint="https://example.com",
            category="AI Model",
            trust_level="media",  # type: ignore[arg-type]
        ),
    )
    raw = RawItem(
        source_id="src",
        title="April headline",
        url="https://example.com/x",
        published_at=datetime(2026, 4, 10, 9, 0),
        raw_summary="news",
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(
        ProcessedItem(
            raw_item_id=raw.id,
            normalized_title="April headline",
            canonical_url="https://example.com/x",
            content_track="expert_news",
            category="AI Model",
            relevance_score=0.9,
            importance_score=1.0,
            summary="news",
        )
    )
    db_session.commit()


def test_monthly_smoke(db_session):
    _seed(db_session)
    result = runner.invoke(app, ["--month", "2026-04"])
    assert result.exit_code == 0, result.output
    assert "2026-04 AI 동향 리포트" in result.output
    assert "April headline" in result.output
    assert "(요약 생략 — LLM 비활성)" in result.output


def test_monthly_html_format(db_session):
    _seed(db_session)
    result = runner.invoke(app, ["--month", "2026-04", "--format", "html"])
    assert result.exit_code == 0, result.output
    assert result.output.lstrip().startswith("<!DOCTYPE html>")
    assert "AI 동향 리포트" in result.output


def test_monthly_save_to_file(tmp_path, db_session):
    _seed(db_session)
    out = tmp_path / "digest.md"
    result = runner.invoke(app, ["--month", "2026-04", "--save", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "AI 동향 리포트" in out.read_text(encoding="utf-8")


def test_monthly_rejects_bad_format(db_session):
    result = runner.invoke(app, ["--month", "2026-04", "--format", "pdf"])
    assert result.exit_code != 0
