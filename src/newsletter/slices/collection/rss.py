"""Generic RSS / Atom collector backed by feedparser.

Fetched with httpx (so respx can mock in tests), then handed to
``feedparser.parse`` which is tolerant of malformed feeds.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import feedparser
import httpx

from newsletter.models.source import Source
from newsletter.slices.collection.base import CollectorError, CollectorResult


def _struct_time_to_datetime(st: time.struct_time | None) -> datetime | None:
    if st is None:
        return None
    try:
        return datetime(*st[:6], tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _extract_content(entry: dict[str, Any]) -> str | None:
    content = entry.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            return first.get("value")
    return None


class RSSCollector:
    """Adapter for ``RSS`` and ``YOUTUBE_RSS`` sources."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "newsletter-collector/0.1"},
        )
        self._owns_client = client is None

    def collect(self, source: Source) -> list[CollectorResult]:
        try:
            response = self._client.get(source.endpoint)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CollectorError(f"RSS fetch failed for {source.endpoint}: {exc}") from exc

        parsed = feedparser.parse(response.content)

        if parsed.bozo and not parsed.entries:
            # bozo + no entries = unparseable. bozo alone (with entries) is fine —
            # feedparser flags minor issues but recovers.
            raise CollectorError(
                f"Could not parse feed at {source.endpoint}: {parsed.bozo_exception!r}"
            )

        results: list[CollectorResult] = []
        for entry in parsed.entries:
            url = entry.get("link")
            if not url:
                continue
            title = (entry.get("title") or "").strip()
            published = _struct_time_to_datetime(
                entry.get("published_parsed") or entry.get("updated_parsed")
            )
            results.append(
                CollectorResult(
                    title=title or url,
                    url=url,
                    published_at=published,
                    author=entry.get("author"),
                    raw_summary=entry.get("summary") or None,
                    raw_content=_extract_content(entry),
                    language=source.language,
                )
            )
        return results

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
