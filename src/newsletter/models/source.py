"""Source registry model.

Implements spec §11 / §19.1. Stored as a single ``sources`` table with
CHECK constraints emulating enums (SQLite-friendly).
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from newsletter.core.db import Base

SOURCE_TYPES: Final = ("NAVER_API", "RSS", "YOUTUBE_RSS", "API", "MANUAL")
CONTENT_TRACKS: Final = ("expert_news", "practical_insight", "both")
PRIORITIES: Final = ("high", "medium", "low")
TRUST_LEVELS: Final = ("official", "media", "community")
FETCH_INTERVALS: Final = ("hourly", "daily", "weekly")
AUDIENCE_LEVELS: Final = ("beginner", "intermediate", "expert")


def _in_clause(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class Source(Base):
    """A configured data source (Naver query, RSS feed, YouTube channel, etc.)."""

    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(_in_clause("type", SOURCE_TYPES), name="ck_sources_type"),
        CheckConstraint(
            _in_clause("content_track", CONTENT_TRACKS), name="ck_sources_content_track"
        ),
        CheckConstraint(_in_clause("priority", PRIORITIES), name="ck_sources_priority"),
        CheckConstraint(_in_clause("trust_level", TRUST_LEVELS), name="ck_sources_trust_level"),
        CheckConstraint(
            _in_clause("fetch_interval", FETCH_INTERVALS),
            name="ck_sources_fetch_interval",
        ),
    )

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(32))
    content_track: Mapped[str] = mapped_column(String(32))
    endpoint: Mapped[str] = mapped_column(String(1024))
    query: Mapped[str | None] = mapped_column(String(500))
    language: Mapped[str | None] = mapped_column(String(8))
    region: Mapped[str | None] = mapped_column(String(16))
    category: Mapped[str | None] = mapped_column(String(64))
    audience_level: Mapped[str | None] = mapped_column(String(16))
    priority: Mapped[str] = mapped_column(String(8), default="medium")
    trust_level: Mapped[str] = mapped_column(String(16), default="media")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    fetch_interval: Mapped[str] = mapped_column(String(16), default="daily")
    auth_required: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_limit_note: Mapped[str | None] = mapped_column(String(500))
    owner: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"Source(id={self.source_id!r}, type={self.type!r}, enabled={self.enabled})"
