"""SQLAlchemy ORM models shared across slices.

Models are added here as slices implement them. Importing ``newsletter.models``
ensures all models are registered with ``Base.metadata`` for Alembic autogen.
"""

from newsletter.models.company_interest import CompanyInterest
from newsletter.models.context_chunk import ContextChunk
from newsletter.models.department import Department
from newsletter.models.department_tip import DepartmentTip
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.models.run_log import RunLog
from newsletter.models.source import Source

__all__ = [
    "CompanyInterest",
    "ContextChunk",
    "Department",
    "DepartmentTip",
    "NewsletterIssue",
    "ProcessedItem",
    "RawItem",
    "RunLog",
    "Source",
]
