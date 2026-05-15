"""Processed items (spec §19.3).

One row per :class:`RawItem` after normalization, dedup, relevance, and
track classification. ``raw_item_id`` is unique — processing is idempotent.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
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
from newsletter.models.source import CONTENT_TRACKS


def _in_clause(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class ProcessedItem(Base):
    """A RawItem normalized + classified, ready for integration/scoring."""

    __tablename__ = "processed_items"
    __table_args__ = (
        UniqueConstraint("raw_item_id", name="uq_processed_items_raw_item_id"),
        CheckConstraint(
            _in_clause("content_track", CONTENT_TRACKS),
            name="ck_processed_items_content_track",
        ),
        Index("ix_processed_items_canonical_url", "canonical_url"),
        Index("ix_processed_items_duplicate_group_id", "duplicate_group_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_item_id: Mapped[int] = mapped_column(
        ForeignKey("raw_items.id", ondelete="CASCADE"),
        index=True,
    )
    normalized_title: Mapped[str] = mapped_column(String(1000))
    canonical_url: Mapped[str] = mapped_column(String(2048))
    content_track: Mapped[str] = mapped_column(String(32))
    category: Mapped[str | None] = mapped_column(String(64))
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    importance_score: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[str | None] = mapped_column(String(500))
    duplicate_group_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return (
            f"ProcessedItem(id={self.id}, raw_item_id={self.raw_item_id}, "
            f"track={self.content_track!r}, rel={self.relevance_score:.2f})"
        )
