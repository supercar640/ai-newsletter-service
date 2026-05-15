"""extend sources type CHECK to include YOUTUBE_SEARCH

Revision ID: 7fefd2fe33c8
Revises: c516264ee115
Create Date: 2026-05-15 16:21:45.251274

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401 — imported by template
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7fefd2fe33c8"
down_revision: str | Sequence[str] | None = "c516264ee115"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_TYPES = "type IN ('NAVER_API', 'RSS', 'YOUTUBE_RSS', 'API', 'MANUAL')"
_NEW_TYPES = "type IN ('NAVER_API', 'RSS', 'YOUTUBE_RSS', 'YOUTUBE_SEARCH', 'API', 'MANUAL')"


def upgrade() -> None:
    """Replace ck_sources_type with one that allows YOUTUBE_SEARCH."""
    with op.batch_alter_table("sources") as batch_op:
        batch_op.drop_constraint("ck_sources_type", type_="check")
        batch_op.create_check_constraint("ck_sources_type", _NEW_TYPES)


def downgrade() -> None:
    """Restore the previous ck_sources_type."""
    with op.batch_alter_table("sources") as batch_op:
        batch_op.drop_constraint("ck_sources_type", type_="check")
        batch_op.create_check_constraint("ck_sources_type", _OLD_TYPES)
