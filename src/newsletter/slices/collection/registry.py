"""Map a ``source.type`` to the right collector implementation."""

from __future__ import annotations

from newsletter.core.run_context import RunContext
from newsletter.slices.collection.base import Collector, UnsupportedSourceTypeError
from newsletter.slices.collection.naver import NaverCollector
from newsletter.slices.collection.rss import RSSCollector
from newsletter.slices.collection.youtube import YouTubeCollector
from newsletter.slices.collection.youtube_search import YouTubeSearchCollector


def get_collector(source_type: str, *, run_context: RunContext | None = None) -> Collector:
    """Return a fresh collector instance for ``source_type``.

    Each call constructs a new collector so callers can close it after
    one source. The function does not memoize — collectors hold open
    HTTP clients (and, for YOUTUBE_SEARCH, a Whisper model handle).
    """
    if source_type == "NAVER_API":
        return NaverCollector()
    if source_type == "RSS":
        return RSSCollector()
    if source_type == "YOUTUBE_RSS":
        return YouTubeCollector()
    if source_type == "YOUTUBE_SEARCH":
        return YouTubeSearchCollector(run_context=run_context)
    raise UnsupportedSourceTypeError(source_type)
