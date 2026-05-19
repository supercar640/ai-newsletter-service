"""add audience column to newsletter_issues

Revision ID: 4f66b396d632
Revises: 9638e8b6379e
Create Date: 2026-05-19 11:49:05.116730

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4f66b396d632'
down_revision: str | Sequence[str] | None = '9638e8b6379e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("newsletter_issues", schema=None) as batch_op:
        batch_op.add_column(sa.Column("audience", sa.String(length=16), nullable=True))
        batch_op.create_check_constraint(
            "ck_newsletter_issues_audience",
            "audience IS NULL OR audience IN ('general', 'executive', 'technical')",
        )
        batch_op.create_index("ix_newsletter_issues_audience", ["audience"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("newsletter_issues", schema=None) as batch_op:
        batch_op.drop_index("ix_newsletter_issues_audience")
        batch_op.drop_constraint("ck_newsletter_issues_audience", type_="check")
        batch_op.drop_column("audience")
