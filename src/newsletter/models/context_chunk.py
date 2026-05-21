"""ContextChunk — one chunk of an internal company document.

The corpus indexer splits files under ``COMPANY_CONTEXT_DIR`` into chunks,
embeds each, and stores them here. The importance scorer matches news items
against these chunks (embedding cosine, or keyword overlap when no embedding)
to boost company-relevant news.

``source_path`` + ``file_hash`` drive incremental re-indexing: all chunks of
a file share the file's content hash, so an unchanged file is skipped.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from newsletter.core.db import Base


class ContextChunk(Base):
    """One chunk of an internal document, embedded for relevance scoring."""

    __tablename__ = "context_chunks"
    __table_args__ = (
        UniqueConstraint(
            "source_path", "chunk_index", name="uq_context_chunks_path_index"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_path: Mapped[str] = mapped_column(String(500))
    file_hash: Mapped[str] = mapped_column(String(64))
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return (
            f"ContextChunk(id={self.id}, source_path={self.source_path!r}, "
            f"chunk_index={self.chunk_index})"
        )
