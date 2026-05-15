"""Naver Search Open API news collector.

Pipeline:

1. Call the Naver search endpoint for the source's query.
2. Keep only items whose ``link`` is a Naver-hosted article
   (``n.news.naver.com``) — that host has a stable, parseable DOM.
3. For each kept item, fetch the article page and extract the body
   text into ``raw_content``. Body fetches that fail (network / parse
   errors) are logged but do not drop the item; we just leave the body
   ``None``.

The canonical URL stored on :class:`CollectorResult` is ``originallink``
(the publisher's URL) when present, falling back to ``link``. This keeps
cross-source dedup correct (the same article that shows up via a
publisher RSS will match) while still letting us reach the parseable
Naver mirror for body extraction.

Endpoint: ``https://openapi.naver.com/v1/search/news.json``
Docs: https://developers.naver.com/docs/serviceapi/search/news/news.md

Requires ``NAVER_CLIENT_ID`` / ``NAVER_CLIENT_SECRET`` in the environment.
"""

from __future__ import annotations

import html
import re
from email.utils import parsedate_to_datetime

import httpx

from newsletter.core.config import get_settings
from newsletter.core.logging import get_logger
from newsletter.models.source import Source
from newsletter.slices.collection.base import CollectorError, CollectorResult
from newsletter.slices.collection.naver_article import (
    extract_article_body,
    is_naver_news_url,
)

log = get_logger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    return html.unescape(_TAG_RE.sub("", value)).strip()


class NaverCollector:
    """Adapter for the Naver Search news endpoint with body extraction."""

    URL = "https://openapi.naver.com/v1/search/news.json"
    DEFAULT_DISPLAY = 100
    _BROWSER_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        fetch_bodies: bool = True,
    ) -> None:
        settings = get_settings()
        self._client_id = settings.naver_client_id
        self._client_secret = settings.naver_client_secret
        self._client = client or httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": self._BROWSER_UA},
        )
        self._owns_client = client is None
        self._fetch_bodies = fetch_bodies

    def collect(self, source: Source) -> list[CollectorResult]:
        if not source.query:
            return []
        if not self._client_id or not self._client_secret:
            raise CollectorError(
                "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET must be set to use NAVER_API sources"
            )

        try:
            response = self._client.get(
                self.URL,
                params={
                    "query": source.query,
                    "display": self.DEFAULT_DISPLAY,
                    "sort": "date",
                },
                headers={
                    "X-Naver-Client-Id": self._client_id,
                    "X-Naver-Client-Secret": self._client_secret,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CollectorError(f"Naver request failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise CollectorError(f"Naver returned non-JSON body: {exc}") from exc

        items = data.get("items") or []
        results: list[CollectorResult] = []
        skipped_non_naver = 0
        for item in items:
            naver_link = item.get("link") or ""
            if not is_naver_news_url(naver_link):
                skipped_non_naver += 1
                continue

            canonical_url = item.get("originallink") or naver_link
            body = self._fetch_body(naver_link) if self._fetch_bodies else None

            results.append(
                CollectorResult(
                    title=_strip_html(item.get("title")),
                    url=canonical_url,
                    published_at=_parse_pubdate(item.get("pubDate")),
                    author=None,
                    raw_summary=_strip_html(item.get("description")) or None,
                    raw_content=body,
                    language=source.language or "ko",
                )
            )

        if skipped_non_naver:
            log.info(
                "naver.filter",
                source=source.source_id,
                kept=len(results),
                skipped_non_naver=skipped_non_naver,
            )
        return results

    def _fetch_body(self, url: str) -> str | None:
        try:
            page = self._client.get(url)
            page.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("naver.body.fetch_failed", url=url, error=str(exc))
            return None

        try:
            return extract_article_body(page.text)
        except Exception as exc:
            log.warning("naver.body.parse_failed", url=url, error=str(exc))
            return None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def _parse_pubdate(raw: str | None):
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
