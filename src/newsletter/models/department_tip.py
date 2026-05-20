"""DepartmentTip — accumulated per-department usage tips, one row per
(issue, department).

History table for the "부서별 활용 팁" section. Past tips are fed back into the
generator as "avoid repeating these" so successive issues stay varied. The
department name is denormalized (string, not FK) so editing or deleting a
:class:`Department` row never orphans accumulated history.
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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from newsletter.core.db import Base


class DepartmentTip(Base):
    """One generated department tip, tied to the issue it shipped in."""

    __tablename__ = "department_tips"
    __table_args__ = (
        Index("ix_department_tips_dept_created", "department", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(
        ForeignKey("newsletter_issues.id", ondelete="CASCADE")
    )
    department: Mapped[str] = mapped_column(String(100))
    tip: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"DepartmentTip(id={self.id}, issue_id={self.issue_id}, department={self.department!r})"
