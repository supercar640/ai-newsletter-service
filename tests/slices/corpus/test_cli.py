"""corpus CLI smoke tests."""

from __future__ import annotations

from typer.testing import CliRunner

from newsletter.slices.corpus import repository
from newsletter.slices.corpus.cli import app

runner = CliRunner()


def test_index_without_dir_configured_warns(db_session, monkeypatch):
    monkeypatch.setenv("COMPANY_CONTEXT_DIR", "")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()
    result = runner.invoke(app, ["index"])
    assert result.exit_code == 0
    assert "COMPANY_CONTEXT_DIR" in result.output


def test_index_indexes_directory(tmp_path, db_session, monkeypatch):
    (tmp_path / "doc.md").write_text("# 제목\nrag agent 내용", encoding="utf-8")
    monkeypatch.setenv("COMPANY_CONTEXT_DIR", str(tmp_path))
    # No embedding key -> DisabledEmbeddingClient (never hits the real API).
    monkeypatch.setenv("VOYAGE_API_KEY", "")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()
    result = runner.invoke(app, ["index"])
    assert result.exit_code == 0, result.output
    db_session.expire_all()
    assert len(repository.list_chunks(db_session)) >= 1


def test_clear_removes_chunks(db_session, monkeypatch):
    from newsletter.slices.corpus.repository import ChunkInsert

    repository.replace_file_chunks(
        db_session,
        source_path="a.md",
        file_hash="h1",
        chunks=[ChunkInsert(text="c", keywords=[], embedding=None, embedding_model=None)],
    )
    db_session.commit()
    result = runner.invoke(app, ["clear"])
    assert result.exit_code == 0
    db_session.expire_all()
    assert repository.list_chunks(db_session) == []


def test_list_empty(db_session):
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "no chunks" in result.output.lower()
