"""trends CLI smoke tests."""

from __future__ import annotations

from datetime import datetime

from typer.testing import CliRunner

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate
from newsletter.slices.trends.cli import app

runner = CliRunner()


def _seed_source(db_session) -> None:
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


def _seed(db_session, *, title: str, published_at: datetime) -> None:
    raw = RawItem(
        source_id="src",
        title=title,
        url=f"https://example.com/{title[:20]}-{published_at}",
        published_at=published_at,
        raw_summary=title,
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    proc = ProcessedItem(
        raw_item_id=raw.id,
        normalized_title=title,
        canonical_url=raw.url,
        content_track="expert_news",
        category="AI Model",
        relevance_score=0.9,
        importance_score=1.0,
        summary=title,
        keywords=None,
        duplicate_group_id=None,
    )
    db_session.add(proc)
    db_session.flush()


def test_trends_empty_window(db_session):
    result = runner.invoke(app, ["--period", "week", "--end", "2026-05-21"])
    assert result.exit_code == 0
    assert "no items in window" in result.output.lower()


def test_trends_reports_new_term(db_session):
    _seed_source(db_session)
    _seed(db_session, title="Sora video model launch", published_at=datetime(2026, 5, 18, 9, 0))
    db_session.commit()
    result = runner.invoke(app, ["--period", "week", "--end", "2026-05-21", "--min-count", "1"])
    assert result.exit_code == 0, result.output
    assert "sora" in result.output.lower()


def test_trends_saves_to_file(tmp_path, db_session):
    _seed_source(db_session)
    _seed(db_session, title="Sora video model", published_at=datetime(2026, 5, 18, 9, 0))
    db_session.commit()
    out = tmp_path / "trends.md"
    result = runner.invoke(
        app,
        ["--period", "week", "--end", "2026-05-21", "--min-count", "1", "--save", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "트렌드 리포트" in out.read_text(encoding="utf-8")


def test_trends_html_format(db_session):
    _seed_source(db_session)
    _seed(db_session, title="Sora video model", published_at=datetime(2026, 5, 18, 9, 0))
    db_session.commit()
    result = runner.invoke(
        app,
        ["--period", "week", "--end", "2026-05-21", "--min-count", "1", "--format", "html"],
    )
    assert result.exit_code == 0, result.output
    assert result.output.lstrip().startswith("<!DOCTYPE html>")
    assert "트렌드 리포트" in result.output


def test_trends_rejects_bad_format(db_session):
    result = runner.invoke(app, ["--period", "week", "--end", "2026-05-21", "--format", "xml"])
    assert result.exit_code != 0
