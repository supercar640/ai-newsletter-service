"""Data access for ContextChunk rows.

Pure functions over a SQLAlchemy session. Keywords are stored as JSON text;
the repository handles (de)serialization so callers deal in ``list[str]``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from newsletter.models.context_chunk import ContextChunk


@dataclass(frozen=True, slots=True)
class ChunkInsert:
    """One chunk to persist for a file."""

    text: str
    keywords: list[str]
    embedding: bytes | None
    embedding_model: str | None


def file_hashes(session: Session) -> dict[str, str]:
    """Return ``{source_path: file_hash}`` for incremental re-index checks."""
    rows = session.execute(select(ContextChunk.source_path, ContextChunk.file_hash)).all()
    return {path: file_hash for path, file_hash in rows}


def replace_file_chunks(
    session: Session,
    *,
    source_path: str,
    file_hash: str,
    chunks: Sequence[ChunkInsert],
) -> int:
    """Delete a file's existing chunks, then insert the new set. Returns count."""
    session.execute(delete(ContextChunk).where(ContextChunk.source_path == source_path))
    for index, chunk in enumerate(chunks):
        session.add(
            ContextChunk(
                source_path=source_path,
                file_hash=file_hash,
                chunk_index=index,
                text=chunk.text,
                keywords_json=_dump_keywords(chunk.keywords),
                embedding=chunk.embedding,
                embedding_model=chunk.embedding_model,
            )
        )
    session.flush()
    return len(chunks)


def list_chunks(session: Session) -> list[ContextChunk]:
    stmt = select(ContextChunk).order_by(ContextChunk.source_path, ContextChunk.chunk_index)
    return list(session.scalars(stmt).all())


def delete_all(session: Session) -> int:
    """Delete every chunk. Returns the number of rows removed."""
    rows = session.scalars(select(ContextChunk)).all()
    for row in rows:
        session.delete(row)
    session.flush()
    return len(rows)


def load_keywords(row: ContextChunk) -> list[str]:
    """Parse the JSON keywords column. Tolerant of malformed payloads."""
    try:
        parsed = json.loads(row.keywords_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(k) for k in parsed if k]


def _dump_keywords(keywords: Sequence[str]) -> str:
    cleaned = [k.strip() for k in keywords if k and k.strip()]
    return json.dumps(cleaned, ensure_ascii=False)


__all__ = [
    "ChunkInsert",
    "delete_all",
    "file_hashes",
    "list_chunks",
    "load_keywords",
    "replace_file_chunks",
]
