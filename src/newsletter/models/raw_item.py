"""Raw collected items (spec §19.2).

One row per item as it arrived from a source, before any normalization
or filtering. Uniqueness is enforced on ``(source_id, url)`` so the same
article can co-exist across multiple sources but not duplicate within
one source.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from newsletter.core.db import Base


class RawItem(Base):
    """One collected item from a source, before processing."""

    __tablename__ = "raw_items"
    __table_args__ = (
        UniqueConstraint("source_id", "url", name="uq_raw_items_source_url"),
        Index("ix_raw_items_collected_at", "collected_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.source_id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(1000))
    url: Mapped[str] = mapped_column(String(2048))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    author: Mapped[str | None] = mapped_column(String(200))
    raw_summary: Mapped[str | None] = mapped_column(Text)
    raw_content: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(8))

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"RawItem(id={self.id}, source={self.source_id!r}, url={self.url!r})"
