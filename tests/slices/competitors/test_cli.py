"""competitors CLI smoke tests."""

from __future__ import annotations

from datetime import datetime

from typer.testing import CliRunner

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.competitors import repository
from newsletter.slices.competitors.cli import app
from newsletter.slices.competitors.schemas import CompetitorCreate
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate

runner = CliRunner()


def test_add_then_list(db_session):
    result = runner.invoke(app, ["add", "--name", "OpenAI", "--aliases", "openai,gpt"])
    assert result.exit_code == 0, result.output
    assert "competitor 추가 완료" in result.output

    db_session.expire_all()
    rows = repository.list_competitors(db_session)
    assert len(rows) == 1
    assert rows[0].name == "OpenAI"

    listed = runner.invoke(app, ["list"])
    assert listed.exit_code == 0
    assert "OpenAI" in listed.output


def test_report_without_competitors_is_graceful(db_session):
    result = runner.invoke(app, ["report"])
    assert result.exit_code == 0
    assert "no competitors registered" in result.output


def test_report_smoke(db_session):
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
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai"]))
    raw = RawItem(
        source_id="src",
        title="OpenAI ships",
        url="https://example.com/x",
        published_at=datetime(2026, 5, 20, 9, 0),
        raw_summary="news",
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(
        ProcessedItem(
            raw_item_id=raw.id,
            normalized_title="OpenAI ships",
            canonical_url="https://example.com/x",
            content_track="expert_news",
            category="AI Model",
            relevance_score=0.9,
            importance_score=1.0,
            summary="news",
        )
    )
    db_session.commit()

    result = runner.invoke(app, ["report", "--since", "2026-05-15", "--until", "2026-05-22"])
    assert result.exit_code == 0, result.output
    assert "OpenAI" in result.output


def test_report_save_writes_file(db_session, tmp_path):
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai"]))
    db_session.commit()
    out = tmp_path / "report.md"
    result = runner.invoke(
        app,
        ["report", "--since", "2026-05-15", "--until", "2026-05-22", "--save", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "경쟁사 멘션 리포트" in out.read_text(encoding="utf-8")
