"""Competitor — operator-registered companies/products to track in mentions.

Each row is one competitor. ``aliases_json`` holds the product/brand names
that the mention report matches against the title + summary of accumulated
ProcessedItems. Detection is deterministic alias matching — no embedding.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from newsletter.core.db import Base


class Competitor(Base):
    """One competitor the operator wants to track across collected items."""

    __tablename__ = "competitors"
    __table_args__ = (UniqueConstraint("name", name="uq_competitors_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    aliases_json: Mapped[str] = mapped_column(Text, default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"Competitor(id={self.id}, name={self.name!r}, enabled={self.enabled})"
