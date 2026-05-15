"""YouTube collector — video id extraction + Data API v3 enrichment."""

from __future__ import annotations

import httpx
import pytest
import respx

from newsletter.models.source import Source
from newsletter.slices.collection.youtube import YouTubeCollector, extract_video_id


def _settings_with_youtube_key(monkeypatch: pytest.MonkeyPatch, key: str = "yt-test") -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", key)
    monkeypatch.setenv("YOUTUBE_FETCH_METADATA", "1")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()


def _settings_with_no_youtube_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "")
    monkeypatch.setenv("YOUTUBE_FETCH_METADATA", "1")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()


def test_extract_video_id_from_various_formats() -> None:
    # Real YouTube ids are exactly 11 characters from [A-Za-z0-9_-].
    assert extract_video_id("https://www.youtube.com/watch?v=ID11char001") == "ID11char001"
    assert extract_video_id("https://youtu.be/ID11char002") == "ID11char002"
    assert (
        extract_video_id("https://www.youtube.com/watch?feature=share&v=ID11char003")
        == "ID11char003"
    )
    assert extract_video_id("https://www.youtube.com/shorts/ID11char004") == "ID11char004"
    assert extract_video_id("https://example.com/not-youtube") is None
    assert extract_video_id("") is None
    assert extract_video_id(None) is None


@respx.mock
def test_youtube_enriches_items_with_description(
    youtube_source: Source,
    youtube_feed_xml: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_youtube_key(monkeypatch)
    respx.get(youtube_source.endpoint).mock(
        return_value=httpx.Response(200, content=youtube_feed_xml),
    )
    respx.get(YouTubeCollector.DATA_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "abcABC12345",
                        "snippet": {
                            "title": "Building agents with Claude",
                            "description": "How to design tool-using agents.\n\nLine 2.",
                            "channelTitle": "Anthropic",
                        },
                    },
                    {
                        "id": "defDEF98765",
                        "snippet": {
                            "title": "Tool use deep dive",
                            "description": "Deep dive into tool use.",
                            "channelTitle": "Anthropic",
                        },
                    },
                ]
            },
        ),
    )

    collector = YouTubeCollector()
    try:
        results = collector.collect(youtube_source)
    finally:
        collector.close()

    by_url = {r.url: r for r in results}
    abc = by_url["https://www.youtube.com/watch?v=abcABC12345"]
    # raw_content is replaced with the Data API description.
    assert abc.raw_content == "How to design tool-using agents.\n\nLine 2."
    assert abc.author == "Anthropic"
    # raw_summary from the Atom feed is preserved (we don't overwrite an
    # existing summary with the API description).
    assert abc.raw_summary == "How to build coding agents with Claude."

    defv = by_url["https://www.youtube.com/watch?v=defDEF98765"]
    assert defv.raw_content == "Deep dive into tool use."


@respx.mock
def test_youtube_skips_enrichment_when_key_missing(
    youtube_source: Source,
    youtube_feed_xml: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_no_youtube_key(monkeypatch)
    respx.get(youtube_source.endpoint).mock(
        return_value=httpx.Response(200, content=youtube_feed_xml),
    )
    api_route = respx.get(YouTubeCollector.DATA_API_URL).mock(
        return_value=httpx.Response(200, json={"items": []}),
    )

    collector = YouTubeCollector()
    try:
        results = collector.collect(youtube_source)
    finally:
        collector.close()

    assert api_route.call_count == 0
    assert len(results) == 2
    assert all(r.raw_content is None for r in results)


@respx.mock
def test_youtube_skips_enrichment_when_flag_off(
    youtube_source: Source,
    youtube_feed_xml: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt-test")
    monkeypatch.setenv("YOUTUBE_FETCH_METADATA", "0")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()

    respx.get(youtube_source.endpoint).mock(
        return_value=httpx.Response(200, content=youtube_feed_xml),
    )
    api_route = respx.get(YouTubeCollector.DATA_API_URL).mock(
        return_value=httpx.Response(200, json={"items": []}),
    )

    collector = YouTubeCollector()
    try:
        results = collector.collect(youtube_source)
    finally:
        collector.close()

    assert api_route.call_count == 0
    assert len(results) == 2


@respx.mock
def test_youtube_calls_data_api_with_key_and_ids(
    youtube_source: Source,
    youtube_feed_xml: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_youtube_key(monkeypatch, key="my-key")
    respx.get(youtube_source.endpoint).mock(
        return_value=httpx.Response(200, content=youtube_feed_xml),
    )
    api_route = respx.get(YouTubeCollector.DATA_API_URL).mock(
        return_value=httpx.Response(200, json={"items": []}),
    )

    collector = YouTubeCollector()
    try:
        collector.collect(youtube_source)
    finally:
        collector.close()

    assert api_route.called
    req = api_route.calls.last.request
    assert req.url.params["key"] == "my-key"
    assert req.url.params["part"] == "snippet,statistics"
    ids = req.url.params["id"].split(",")
    # video ids extracted and sorted from the fixture feed.
    assert set(ids) == {"abcABC12345", "defDEF98765"}


@respx.mock
def test_youtube_api_failure_is_not_fatal(
    youtube_source: Source,
    youtube_feed_xml: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_youtube_key(monkeypatch)
    respx.get(youtube_source.endpoint).mock(
        return_value=httpx.Response(200, content=youtube_feed_xml),
    )
    respx.get(YouTubeCollector.DATA_API_URL).mock(return_value=httpx.Response(500))

    collector = YouTubeCollector()
    try:
        results = collector.collect(youtube_source)
    finally:
        collector.close()

    # Items survive without descriptions.
    assert len(results) == 2
    assert all(r.raw_content is None for r in results)


@respx.mock
def test_youtube_partial_api_response(
    youtube_source: Source,
    youtube_feed_xml: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """API returns only one of two videos — the other stays un-enriched."""
    _settings_with_youtube_key(monkeypatch)
    respx.get(youtube_source.endpoint).mock(
        return_value=httpx.Response(200, content=youtube_feed_xml),
    )
    respx.get(YouTubeCollector.DATA_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "abcABC12345",
                        "snippet": {
                            "description": "only abc enriched",
                            "channelTitle": "Anthropic",
                        },
                    }
                ]
            },
        ),
    )

    collector = YouTubeCollector()
    try:
        results = collector.collect(youtube_source)
    finally:
        collector.close()

    by_url = {r.url: r for r in results}
    assert by_url["https://www.youtube.com/watch?v=abcABC12345"].raw_content == "only abc enriched"
    assert by_url["https://www.youtube.com/watch?v=defDEF98765"].raw_content is None
