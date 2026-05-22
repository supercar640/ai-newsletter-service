"""departments digest CLI smoke tests. No VOYAGE key in tests, so the digest
runs in keyword mode — output is deterministic."""

from __future__ import annotations

from datetime import datetime

from typer.testing import CliRunner

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.departments import repository
from newsletter.slices.departments.cli import app
from newsletter.slices.departments.schemas import DepartmentCreate
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
    repository.add(db_session, DepartmentCreate(name="영업", description="고객 매출"))
    raw = RawItem(
        source_id="src",
        title="고객 매출 분석",
        url="https://example.com/x",
        published_at=datetime(2026, 5, 20, 9, 0),
        raw_summary="영업 성과",
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(
        ProcessedItem(
            raw_item_id=raw.id,
            normalized_title="고객 매출 분석",
            canonical_url="https://example.com/x",
            content_track="expert_news",
            category="AI Model",
            relevance_score=0.9,
            importance_score=1.0,
            summary="영업 성과",
        )
    )
    db_session.commit()


def test_digest_smoke(db_session):
    _seed(db_session)
    result = runner.invoke(app, ["digest", "--since", "2026-05-15", "--until", "2026-05-22"])
    assert result.exit_code == 0, result.output
    assert "부서별 다이제스트" in result.output
    assert "영업" in result.output
    assert "고객 매출 분석" in result.output


def test_digest_html_format(db_session):
    _seed(db_session)
    result = runner.invoke(
        app, ["digest", "--since", "2026-05-15", "--until", "2026-05-22", "--format", "html"]
    )
    assert result.exit_code == 0, result.output
    assert result.output.lstrip().startswith("<!DOCTYPE html>")
    assert "부서별 다이제스트" in result.output


def test_digest_save_to_file(tmp_path, db_session):
    _seed(db_session)
    out = tmp_path / "dept.md"
    result = runner.invoke(
        app, ["digest", "--since", "2026-05-15", "--until", "2026-05-22", "--save", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "부서별 다이제스트" in out.read_text(encoding="utf-8")


def test_digest_rejects_bad_format(db_session):
    result = runner.invoke(app, ["digest", "--format", "pdf"])
    assert result.exit_code != 0
