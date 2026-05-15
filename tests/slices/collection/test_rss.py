"""RSS and YouTube RSS collectors."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from newsletter.models.source import Source
from newsletter.slices.collection.base import CollectorError
from newsletter.slices.collection.rss import RSSCollector
from newsletter.slices.collection.youtube import YouTubeCollector


@respx.mock
def test_rss_collect_parses_items(rss_source: Source, rss_feed_xml: bytes) -> None:
    respx.get(rss_source.endpoint).mock(
        return_value=httpx.Response(
            200,
            content=rss_feed_xml,
            headers={"Content-Type": "application/rss+xml"},
        ),
    )

    collector = RSSCollector()
    try:
        results = collector.collect(rss_source)
    finally:
        collector.close()

    assert len(results) == 2
    first = results[0]
    assert first.title == "OpenAI announces o-series"
    assert first.url == "https://example.com/openai-o-series"
    assert first.author == "jane@example.com (Jane Doe)"
    assert first.language == "en"
    assert first.raw_summary is not None and "reasoning models" in first.raw_summary
    assert first.published_at is not None
    assert first.published_at.astimezone(UTC) == datetime(2025, 5, 12, 9, 0, tzinfo=UTC)


@respx.mock
def test_rss_collect_skips_entries_without_link(
    rss_source: Source,
) -> None:
    feed = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <title>x</title><link>https://x</link><description>x</description>
          <item><title>no link</title><description>orphan</description></item>
          <item><title>good</title><link>https://x.example/a</link><description>ok</description></item>
        </channel></rss>"""
    respx.get(rss_source.endpoint).mock(return_value=httpx.Response(200, content=feed))

    collector = RSSCollector()
    try:
        results = collector.collect(rss_source)
    finally:
        collector.close()

    assert len(results) == 1
    assert results[0].url == "https://x.example/a"


@respx.mock
def test_rss_collect_wraps_http_error(rss_source: Source) -> None:
    respx.get(rss_source.endpoint).mock(return_value=httpx.Response(503))
    collector = RSSCollector()
    try:
        with pytest.raises(CollectorError):
            collector.collect(rss_source)
    finally:
        collector.close()


@respx.mock
def test_rss_collect_rejects_unparseable_feed(rss_source: Source) -> None:
    respx.get(rss_source.endpoint).mock(
        return_value=httpx.Response(200, content=b"not xml at all <<<<>>>>"),
    )
    collector = RSSCollector()
    try:
        with pytest.raises(CollectorError):
            collector.collect(rss_source)
    finally:
        collector.close()


@respx.mock
def test_youtube_collect_parses_atom_entries(
    youtube_source: Source, youtube_feed_xml: bytes
) -> None:
    respx.get(youtube_source.endpoint).mock(
        return_value=httpx.Response(
            200,
            content=youtube_feed_xml,
            headers={"Content-Type": "application/atom+xml"},
        ),
    )

    collector = YouTubeCollector()
    try:
        results = collector.collect(youtube_source)
    finally:
        collector.close()

    assert len(results) == 2
    urls = {r.url for r in results}
    assert urls == {
        "https://www.youtube.com/watch?v=abcABC12345",
        "https://www.youtube.com/watch?v=defDEF98765",
    }
    titles = {r.title for r in results}
    assert "Building agents with Claude" in titles
    # YouTube atom feeds use <published>, not <pubDate>.
    pub_dates = [r.published_at for r in results]
    assert all(p is not None for p in pub_dates)
