"""CompanyInterest — operator-curated topics that boost importance scoring.

Each row represents one slice of the company's editorial focus (e.g.
"RAG", "AI 영업 자동화", "엔터프라이즈 보안"). The scoring pass uses two
signals per item:

- **Keyword match** — ``keywords_json`` against the item's title + summary.
- **Embedding cosine** — when ``description`` was embedded at insert time
  and the ProcessedItem also has an embedding, semantic proximity boosts
  even when no keyword overlaps.

The two signals together produce an ``interest_multiplier`` in [1.0, 1.5]
that compounds with the existing ``trust x recency x llm`` score.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from newsletter.core.db import Base


class CompanyInterest(Base):
    """One topic the company wants the newsletter to over-weight."""

    __tablename__ = "company_interests"
    __table_args__ = (UniqueConstraint("name", name="uq_company_interests_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return (
            f"CompanyInterest(id={self.id}, name={self.name!r}, "
            f"weight={self.weight}, enabled={self.enabled})"
        )
