"""SQLAlchemy ORM models shared across slices.

Models are added here as slices implement them. Importing ``newsletter.models``
ensures all models are registered with ``Base.metadata`` for Alembic autogen.
"""

from newsletter.models.raw_item import RawItem
from newsletter.models.source import Source

__all__ = ["RawItem", "Source"]
