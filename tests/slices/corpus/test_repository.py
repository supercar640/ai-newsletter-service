"""corpus.repository — chunk persistence."""

from __future__ import annotations

from newsletter.slices.corpus import repository
from newsletter.slices.corpus.repository import ChunkInsert


def _insert(text: str, keywords: list[str]) -> ChunkInsert:
    return ChunkInsert(
        text=text, keywords=keywords, embedding=None, embedding_model=None
    )


def test_replace_file_chunks_inserts(db_session):
    n = repository.replace_file_chunks(
        db_session,
        source_path="a.md",
        file_hash="h1",
        chunks=[_insert("c0", ["x"]), _insert("c1", ["y"])],
    )
    db_session.commit()
    assert n == 2
    rows = repository.list_chunks(db_session)
    assert [r.chunk_index for r in rows] == [0, 1]
    assert {r.source_path for r in rows} == {"a.md"}


def test_replace_file_chunks_is_idempotent(db_session):
    repository.replace_file_chunks(
        db_session, source_path="a.md", file_hash="h1", chunks=[_insert("c0", [])]
    )
    db_session.commit()
    repository.replace_file_chunks(
        db_session, source_path="a.md", file_hash="h2", chunks=[_insert("new", [])]
    )
    db_session.commit()
    rows = repository.list_chunks(db_session)
    assert len(rows) == 1
    assert rows[0].text == "new"
    assert rows[0].file_hash == "h2"


def test_file_hashes_maps_path_to_hash(db_session):
    repository.replace_file_chunks(
        db_session, source_path="a.md", file_hash="h1",
        chunks=[_insert("c0", []), _insert("c1", [])],
    )
    repository.replace_file_chunks(
        db_session, source_path="b.txt", file_hash="h2", chunks=[_insert("c0", [])]
    )
    db_session.commit()
    assert repository.file_hashes(db_session) == {"a.md": "h1", "b.txt": "h2"}


def test_delete_all_returns_count(db_session):
    repository.replace_file_chunks(
        db_session, source_path="a.md", file_hash="h1",
        chunks=[_insert("c0", []), _insert("c1", [])],
    )
    db_session.commit()
    deleted = repository.delete_all(db_session)
    db_session.commit()
    assert deleted == 2
    assert repository.list_chunks(db_session) == []


def test_load_keywords_tolerates_bad_json(db_session):
    repository.replace_file_chunks(
        db_session, source_path="a.md", file_hash="h1",
        chunks=[_insert("c0", ["alpha", "beta"])],
    )
    db_session.commit()
    row = repository.list_chunks(db_session)[0]
    assert repository.load_keywords(row) == ["alpha", "beta"]
    row.keywords_json = "{not json"
    assert repository.load_keywords(row) == []
