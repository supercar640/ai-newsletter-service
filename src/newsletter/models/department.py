"""Department — operator-curated org units for per-department usage tips.

Each row is one department the newsletter writes a tailored "부서별 활용 팁"
line for (기획·영업·마케팅·기술/설계·관리 …). Deliberately a minimal mirror of
:class:`CompanyInterest` — no embedding/weight/keywords; the only signal is
``description`` (work characteristics), fed to the tips generator as context.
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


class Department(Base):
    """One department the newsletter tailors usage tips for."""

    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("name", name="uq_departments_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"Department(id={self.id}, name={self.name!r}, enabled={self.enabled})"
