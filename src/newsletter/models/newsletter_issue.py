"""NewsletterIssue (spec §19.4) — one row per dated newsletter.

State machine (pipeline view, spec §10 + AGENTS.md):

    drafted → review_required → approved → sent

``rejected`` is a terminal off-ramp from review.

Body fields are populated in stages: ``expert_section_md`` and
``practical_section_md`` by the section writers, then ``markdown_body`` /
``html_body`` by the assembler (Iteration 7). The send code path MUST
refuse any issue whose status is not ``approved``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Final

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from newsletter.core.db import Base

NEWSLETTER_ISSUE_STATUSES: Final = (
    "drafted",
    "review_required",
    "approved",
    "sent",
    "rejected",
)


def _in_clause(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


class NewsletterIssue(Base):
    """A single dated newsletter issue."""

    __tablename__ = "newsletter_issues"
    __table_args__ = (
        CheckConstraint(
            _in_clause("status", NEWSLETTER_ISSUE_STATUSES),
            name="ck_newsletter_issues_status",
        ),
        Index("ix_newsletter_issues_issue_date", "issue_date"),
        Index("ix_newsletter_issues_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="drafted")
    title: Mapped[str] = mapped_column(String(200))
    expert_section_md: Mapped[str | None] = mapped_column(Text)
    practical_section_md: Mapped[str | None] = mapped_column(Text)
    markdown_body: Mapped[str | None] = mapped_column(Text)
    html_body: Mapped[str | None] = mapped_column(Text)
    candidate_ids_json: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(64))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return (
            f"NewsletterIssue(id={self.id}, date={self.issue_date}, "
            f"status={self.status!r})"
        )
