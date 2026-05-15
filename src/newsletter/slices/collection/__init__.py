"""Collection slice: source-specific adapters → ``RawItem``.

Public surface:

- :class:`Collector` protocol + :class:`CollectorResult` schema
- adapters: :class:`NaverCollector`, :class:`RSSCollector`, :class:`YouTubeCollector`
- :func:`get_collector` registry resolver
- :func:`collect_all` orchestrator + :class:`CollectionReport`
- ``newsletter collect`` CLI sub-app
"""

from newsletter.slices.collection.base import (
    Collector,
    CollectorResult,
    UnsupportedSourceTypeError,
)
from newsletter.slices.collection.cli import app as cli_app
from newsletter.slices.collection.registry import get_collector
from newsletter.slices.collection.service import CollectionReport, collect_all

__all__ = [
    "CollectionReport",
    "Collector",
    "CollectorResult",
    "UnsupportedSourceTypeError",
    "cli_app",
    "collect_all",
    "get_collector",
]
