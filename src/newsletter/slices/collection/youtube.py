"""YouTube channel RSS collector + Data API v3 enrichment.

Pipeline:

1. Fetch the channel's Atom feed
   (``https://www.youtube.com/feeds/videos.xml?channel_id=<id>``) via the
   shared :class:`RSSCollector` parent. The feed gives us the title,
   URL, published date, and channel as author.
2. Extract each video's 11-character video id from the URL.
3. Call ``GET https://www.googleapis.com/youtube/v3/videos`` with the
   collected ids (up to 50 per request) to fetch the full description
   and statistics. The description is stored in ``raw_content``.

Caption *download* requires OAuth and is out of scope for MVP — the
public description from videos.list is sufficient for downstream LLM
summarization.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

import httpx

from newsletter.core.config import get_settings
from newsletter.core.logging import get_logger
from newsletter.models.source import Source
from newsletter.slices.collection.base import CollectorResult
from newsletter.slices.collection.rss import RSSCollector

log = get_logger(__name__)

_VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?(?:.*&)?v=|youtu\.be/|youtube\.com/shorts/)"
    r"([A-Za-z0-9_-]{11})"
)


def extract_video_id(url: str | None) -> str | None:
    """Return the 11-char YouTube video id parsed from ``url``, or None."""
    if not url:
        return None
    match = _VIDEO_ID_RE.search(url)
    return match.group(1) if match else None


def _chunked(seq: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


class YouTubeCollector(RSSCollector):
    """RSS collector specialized for YouTube channels.

    Enriches each item's ``raw_content`` with the full video description
    fetched from the YouTube Data API v3. Falls back to RSS-only items
    if ``YOUTUBE_API_KEY`` is unset or enrichment is disabled.
    """

    DATA_API_URL = "https://www.googleapis.com/youtube/v3/videos"
    DATA_API_BATCH = 50  # YouTube Data API maximum ids per call

    def __init__(self, client: httpx.Client | None = None) -> None:
        super().__init__(client)
        settings = get_settings()
        self._api_key = settings.youtube_api_key
        self._enabled = settings.youtube_fetch_metadata

    def collect(self, source: Source) -> list[CollectorResult]:
        items = super().collect(source)
        if not items:
            return items
        if not self._enabled:
            return items
        if not self._api_key:
            log.warning(
                "youtube.no_api_key",
                source=source.source_id,
                hint="set YOUTUBE_API_KEY to enrich items with descriptions",
            )
            return items

        ids_by_url = {item.url: extract_video_id(item.url) for item in items}
        valid_ids = sorted({vid for vid in ids_by_url.values() if vid})
        if not valid_ids:
            return items

        details = self._fetch_video_details(valid_ids, source_id=source.source_id)
        if not details:
            return items

        enriched: list[CollectorResult] = []
        for item in items:
            vid = ids_by_url.get(item.url)
            data = details.get(vid) if vid else None
            if data is None:
                enriched.append(item)
                continue

            snippet = data.get("snippet") or {}
            description = (snippet.get("description") or "").strip() or None
            channel_title = snippet.get("channelTitle")
            enriched.append(
                item.model_copy(
                    update={
                        "raw_content": description,
                        # Prefer channelTitle as author when richer than the RSS author.
                        "author": item.author or channel_title,
                        "raw_summary": item.raw_summary or _summarize(description),
                    }
                )
            )
        return enriched

    def _fetch_video_details(self, video_ids: list[str], *, source_id: str) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for chunk in _chunked(video_ids, self.DATA_API_BATCH):
            try:
                response = self._client.get(
                    self.DATA_API_URL,
                    params={
                        "id": ",".join(chunk),
                        "key": self._api_key,
                        "part": "snippet,statistics",
                    },
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning(
                    "youtube.api.fetch_failed",
                    source=source_id,
                    error=str(exc),
                )
                continue

            try:
                payload = response.json()
            except ValueError as exc:
                log.warning(
                    "youtube.api.bad_json",
                    source=source_id,
                    error=str(exc),
                )
                continue

            for item in payload.get("items") or []:
                vid = item.get("id")
                if vid:
                    result[vid] = item
        return result


def _summarize(description: str | None, *, limit: int = 280) -> str | None:
    """Take the first paragraph of the description as a stand-in summary."""
    if not description:
        return None
    head = description.strip().splitlines()[0].strip()
    if len(head) <= limit:
        return head or None
    return head[: limit - 1].rstrip() + "…"
