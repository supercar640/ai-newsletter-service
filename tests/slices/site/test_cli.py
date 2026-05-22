"""site CLI smoke test."""

from __future__ import annotations

from datetime import datetime

from typer.testing import CliRunner

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.site.cli import app
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
        title="OpenAI ships GPT-5",
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
            normalized_title="OpenAI ships GPT-5",
            canonical_url="https://example.com/x",
            content_track="expert_news",
            category="AI Model",
            relevance_score=0.9,
            importance_score=1.0,
            summary="news",
        )
    )
    db_session.commit()


def test_site_writes_all_files(tmp_path, db_session):
    _seed(db_session)
    out = tmp_path / "site"
    result = runner.invoke(app, ["--out", str(out)])
    assert result.exit_code == 0, result.output
    for name in (
        "index.html",
        "trends.html",
        "competitors.html",
        "monthly.html",
        "dashboard.html",
        "departments.html",
    ):
        assert (out / name).exists(), name
        assert (out / name).read_text(encoding="utf-8").lstrip().startswith("<!DOCTYPE html>")
    index = (out / "index.html").read_text(encoding="utf-8")
    assert 'href="trends.html"' in index
    assert "사이트 생성 완료" in result.output
