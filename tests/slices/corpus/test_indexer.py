"""corpus.indexer — scan a directory, chunk, embed, persist (incremental)."""

from __future__ import annotations

from pathlib import Path

from newsletter.core.embeddings import DisabledEmbeddingClient, deserialize
from newsletter.slices.corpus import repository
from newsletter.slices.corpus.indexer import index_corpus


class _FakeEmbed:
    model = "fake-embed"

    def embed(self, texts):
        # Deterministic non-zero vector per text.
        return [[float(len(t)), 1.0, 0.0, 0.0] for t in texts]


def _write(root: Path, name: str, body: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_index_scans_and_persists_chunks(tmp_path, db_session):
    _write(tmp_path, "doc.md", "# 제목\n첫 문단.\n\n## 둘\n둘째 문단.")
    report = index_corpus(db_session, root=tmp_path, embed_client=_FakeEmbed())
    db_session.commit()
    assert report.scanned == 1
    assert report.indexed == 1
    assert report.skipped == 0
    assert report.chunks == 2
    assert report.embedded == 2
    rows = repository.list_chunks(db_session)
    assert len(rows) == 2
    assert deserialize(rows[0].embedding)  # non-empty vector
    assert rows[0].embedding_model == "fake-embed"


def test_index_skips_unchanged_files(tmp_path, db_session):
    _write(tmp_path, "doc.md", "# 제목\n내용.")
    index_corpus(db_session, root=tmp_path, embed_client=_FakeEmbed())
    db_session.commit()
    report = index_corpus(db_session, root=tmp_path, embed_client=_FakeEmbed())
    db_session.commit()
    assert report.skipped == 1
    assert report.indexed == 0


def test_index_reindexes_changed_file(tmp_path, db_session):
    _write(tmp_path, "doc.md", "# 제목\n옛 내용.")
    index_corpus(db_session, root=tmp_path, embed_client=_FakeEmbed())
    db_session.commit()
    _write(tmp_path, "doc.md", "# 제목\n새 내용 완전히 다름.")
    report = index_corpus(db_session, root=tmp_path, embed_client=_FakeEmbed())
    db_session.commit()
    assert report.indexed == 1
    assert report.skipped == 0
    rows = repository.list_chunks(db_session)
    assert "새 내용" in rows[0].text


def test_index_without_embeddings_stores_keywords_only(tmp_path, db_session):
    _write(tmp_path, "doc.md", "rag agent vector store retrieval")
    report = index_corpus(
        db_session, root=tmp_path, embed_client=DisabledEmbeddingClient()
    )
    db_session.commit()
    assert report.embedded == 0
    row = repository.list_chunks(db_session)[0]
    assert row.embedding is None
    assert "rag" in repository.load_keywords(row)


def test_index_empty_directory(tmp_path, db_session):
    report = index_corpus(db_session, root=tmp_path, embed_client=_FakeEmbed())
    assert report.scanned == 0
    assert report.indexed == 0


def test_index_ignores_empty_content_file(tmp_path, db_session):
    _write(tmp_path, "empty.md", "\n\n   \n")
    report = index_corpus(db_session, root=tmp_path, embed_client=_FakeEmbed())
    db_session.commit()
    assert report.scanned == 1
    assert report.indexed == 0
    assert report.chunks == 0
    assert repository.list_chunks(db_session) == []


def test_index_handles_partial_embedding_response(tmp_path, db_session):
    class _ShortEmbed:
        model = "short"

        def embed(self, texts):
            return [[1.0, 0.0, 0.0, 0.0]]  # one vector regardless of input count

    _write(tmp_path, "doc.md", "# A\n첫 문단.\n\n## B\n둘째 문단.")
    report = index_corpus(db_session, root=tmp_path, embed_client=_ShortEmbed())
    db_session.commit()
    rows = repository.list_chunks(db_session)
    assert len(rows) == 2
    assert rows[0].embedding is not None
    assert rows[1].embedding is None  # second chunk got no vector
    assert report.embedded == 1
