"""YouTube search-based collector with STT.

For each ``YOUTUBE_SEARCH`` source:

1. Call YouTube Data API v3 ``search.list`` with the source's ``query``
   to find candidate videos (relevance-ordered by default).
2. Call ``videos.list`` (snippet + statistics) on those video ids to
   pull view counts.
3. Sort by view count, take the top N (``YOUTUBE_SEARCH_TOP_N``).
4. Optionally download the audio (yt-dlp) and transcribe it
   (faster-whisper). The transcript is stored as ``raw_content`` and
   saved alongside the audio file under the run directory.

This collector deliberately writes large artifacts to disk rather than
the DB. The DB carries the transcript text + a reference path; the
audio file stays on disk.
"""

from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Final

import httpx

from newsletter.core.config import get_settings
from newsletter.core.logging import get_logger
from newsletter.core.run_context import RunContext
from newsletter.models.source import Source
from newsletter.slices.collection.base import CollectorError, CollectorResult
from newsletter.slices.collection.stt import STTError, download_and_transcribe

log = get_logger(__name__)

_SEARCH_URL: Final = "https://www.googleapis.com/youtube/v3/search"
_VIDEOS_URL: Final = "https://www.googleapis.com/youtube/v3/videos"
_SEARCH_PAGE_SIZE: Final = 25  # plenty to pick a top-N from


def _video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _parse_published(value: str | None) -> datetime | None:
    if not value:
        return None
    # YouTube returns RFC3339 like ``2025-05-12T09:00:00Z``.
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None


def _view_count(stats: dict) -> int:
    raw = stats.get("viewCount")
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


class YouTubeSearchCollector:
    """Search YouTube for a keyword, take top N by view count, transcribe."""

    SEARCH_URL = _SEARCH_URL
    VIDEOS_URL = _VIDEOS_URL

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        run_context: RunContext | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = settings.youtube_api_key
        self._region = settings.youtube_search_region
        self._top_n = settings.youtube_search_top_n
        self._stt_enabled = settings.youtube_stt_enabled
        self._client = client or httpx.Client(timeout=60.0, follow_redirects=True)
        self._owns_client = client is None
        self._run_context = run_context

    # --- public API ---------------------------------------------------------

    def collect(self, source: Source) -> list[CollectorResult]:
        if not source.query:
            raise CollectorError(f"YOUTUBE_SEARCH source {source.source_id!r} has no query keyword")
        if not self._api_key:
            raise CollectorError("YOUTUBE_API_KEY must be set to use YOUTUBE_SEARCH sources")

        candidate_ids = self._search_video_ids(source.query)
        if not candidate_ids:
            log.info("yt.search.empty", source=source.source_id, query=source.query)
            return []

        videos = self._fetch_video_details(candidate_ids)
        if not videos:
            return []

        videos.sort(key=lambda v: _view_count(v.get("statistics", {})), reverse=True)
        top = videos[: self._top_n]
        log.info(
            "yt.search.top",
            source=source.source_id,
            query=source.query,
            kept=len(top),
            top_view_counts=[_view_count(v.get("statistics", {})) for v in top],
        )

        results: list[CollectorResult] = []
        for video in top:
            results.append(self._build_result(source, video))
        return results

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # --- internals ----------------------------------------------------------

    def _search_video_ids(self, query: str) -> list[str]:
        try:
            response = self._client.get(
                self.SEARCH_URL,
                params={
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "maxResults": _SEARCH_PAGE_SIZE,
                    "regionCode": self._region,
                    "key": self._api_key,
                    "safeSearch": "moderate",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CollectorError(f"YouTube search failed for {query!r}: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise CollectorError(f"YouTube search returned non-JSON: {exc}") from exc

        ids: list[str] = []
        for item in payload.get("items") or []:
            vid_block = item.get("id") or {}
            if vid_block.get("kind") != "youtube#video":
                continue
            vid = vid_block.get("videoId")
            if vid:
                ids.append(vid)
        return ids

    def _fetch_video_details(self, video_ids: list[str]) -> list[dict]:
        try:
            response = self._client.get(
                self.VIDEOS_URL,
                params={
                    "id": ",".join(video_ids),
                    "part": "snippet,statistics,contentDetails",
                    "key": self._api_key,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CollectorError(f"YouTube videos.list failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise CollectorError(f"YouTube videos.list non-JSON: {exc}") from exc

        return list(payload.get("items") or [])

    def _build_result(self, source: Source, video: dict) -> CollectorResult:
        snippet = video.get("snippet") or {}
        video_id = video.get("id") or ""
        title = (snippet.get("title") or "").strip() or video_id
        description = (snippet.get("description") or "").strip() or None
        channel_title = snippet.get("channelTitle")
        published = _parse_published(snippet.get("publishedAt"))
        url = _video_url(video_id)

        raw_content = description
        if self._stt_enabled and self._run_context and video_id:
            transcript = self._transcribe(video_id, url, source.source_id)
            if transcript is not None:
                raw_content = transcript

        return CollectorResult(
            title=title,
            url=url,
            published_at=published,
            author=channel_title,
            raw_summary=description and _shorten(description),
            raw_content=raw_content,
            language=source.language or snippet.get("defaultAudioLanguage"),
        )

    def _transcribe(self, video_id: str, url: str, source_id: str) -> str | None:
        assert self._run_context is not None  # narrowed by caller
        dest_dir = self._run_context.subdir("youtube", source_id)
        try:
            result = download_and_transcribe(url, video_id, dest_dir)
        except STTError as exc:
            log.warning(
                "yt.stt.failed",
                source=source_id,
                video_id=video_id,
                error=str(exc),
            )
            return None
        return result.text or None


def _shorten(text: str, *, limit: int = 280) -> str:
    """Take the first line, cap at ``limit`` characters."""
    head = text.strip().splitlines()[0].strip()
    if len(head) <= limit:
        return head
    return head[: limit - 1].rstrip() + "…"
