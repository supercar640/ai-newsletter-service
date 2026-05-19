"""SQLAlchemy ORM models shared across slices.

Models are added here as slices implement them. Importing ``newsletter.models``
ensures all models are registered with ``Base.metadata`` for Alembic autogen.
"""

from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.models.run_log import RunLog
from newsletter.models.source import Source

__all__ = ["NewsletterIssue", "ProcessedItem", "RawItem", "RunLog", "Source"]
