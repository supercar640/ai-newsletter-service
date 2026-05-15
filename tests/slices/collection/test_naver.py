"""Naver collector — search + filter + body extraction."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from newsletter.models.source import Source
from newsletter.slices.collection.base import CollectorError
from newsletter.slices.collection.naver import NaverCollector, _strip_html
from newsletter.slices.collection.naver_article import (
    extract_article_body,
    is_naver_news_url,
)


def _settings_with_naver_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()


def _mock_naver_body(html: str = "<html><body>placeholder</body></html>") -> None:
    """Match every fetched n.news.naver.com page with the same HTML body."""
    respx.get(url__regex=r"^https://n\.news\.naver\.com/.*").mock(
        return_value=httpx.Response(200, text=html),
    )


# ---- utility-level tests ----------------------------------------------------


def test_strip_html_removes_tags_and_entities() -> None:
    assert _strip_html("OpenAI <b>GPT-5</b> &quot;released&quot;") == 'OpenAI GPT-5 "released"'
    assert _strip_html("  spaced  ") == "spaced"
    assert _strip_html(None) == ""
    assert _strip_html("") == ""


def test_is_naver_news_url() -> None:
    assert is_naver_news_url("https://n.news.naver.com/mnews/article/001/123") is True
    assert is_naver_news_url("https://news.naver.com/article/001") is False
    assert is_naver_news_url("https://other.example.com") is False
    assert is_naver_news_url(None) is False
    assert is_naver_news_url("") is False


def test_extract_article_body_finds_dic_area(naver_article_html: str) -> None:
    body = extract_article_body(naver_article_html)
    assert body is not None
    assert "첫째 문단" in body
    assert "마지막 문단" in body
    # Inline script content should not appear.
    assert "var a" not in body
    # Excessive whitespace inside lines is collapsed.
    assert "    " not in body


def test_extract_article_body_returns_none_on_unknown_layout() -> None:
    assert extract_article_body("<html><body><p>no body marker</p></body></html>") is None
    assert extract_article_body("") is None


# ---- collector behaviour ----------------------------------------------------


@respx.mock
def test_naver_collect_keeps_naver_links_and_uses_originallink(
    naver_source: Source,
    naver_json_response: dict,
    naver_article_html: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_naver_keys(monkeypatch)
    respx.get(NaverCollector.URL).mock(
        return_value=httpx.Response(200, json=naver_json_response),
    )
    _mock_naver_body(naver_article_html)

    collector = NaverCollector()
    try:
        results = collector.collect(naver_source)
    finally:
        collector.close()

    assert len(results) == 2
    first = results[0]
    # originallink wins as canonical URL
    assert first.url == "https://news.example.com/openai-gpt5"
    assert first.title == 'OpenAI GPT-5 "출시" 임박'
    assert first.raw_summary == "OpenAI가 GPT-5 모델을 공개했다."
    assert first.language == "ko"
    assert first.published_at is not None
    assert first.raw_content is not None  # body fetched + parsed
    assert "첫째 문단" in first.raw_content

    # Item 2 has empty originallink → falls back to link
    second = results[1]
    assert second.url == "https://n.news.naver.com/mnews/article/002/456"


@respx.mock
def test_naver_collect_filters_non_naver_and_empty_links(
    naver_source: Source,
    naver_mixed_links_response: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_naver_keys(monkeypatch)
    respx.get(NaverCollector.URL).mock(
        return_value=httpx.Response(200, json=naver_mixed_links_response),
    )
    _mock_naver_body()

    collector = NaverCollector()
    try:
        results = collector.collect(naver_source)
    finally:
        collector.close()

    assert len(results) == 1
    assert results[0].title == "kept"
    assert results[0].url == "https://news.example.com/keep"


@respx.mock
def test_naver_collect_extracts_body_from_naver_page(
    naver_source: Source,
    naver_json_response: dict,
    naver_article_html: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_naver_keys(monkeypatch)
    respx.get(NaverCollector.URL).mock(
        return_value=httpx.Response(200, json=naver_json_response),
    )
    _mock_naver_body(naver_article_html)

    collector = NaverCollector()
    try:
        results = collector.collect(naver_source)
    finally:
        collector.close()

    assert results[0].raw_content is not None
    assert "첫째 문단" in results[0].raw_content
    assert "마지막 문단" in results[0].raw_content


@respx.mock
def test_naver_body_fetch_failure_is_not_fatal(
    naver_source: Source,
    naver_json_response: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_naver_keys(monkeypatch)
    respx.get(NaverCollector.URL).mock(
        return_value=httpx.Response(200, json=naver_json_response),
    )
    # Body URL returns 500 — item should survive with raw_content=None.
    respx.get(url__regex=r"^https://n\.news\.naver\.com/.*").mock(
        return_value=httpx.Response(500),
    )

    collector = NaverCollector()
    try:
        results = collector.collect(naver_source)
    finally:
        collector.close()

    assert len(results) == 2
    assert all(r.raw_content is None for r in results)


@respx.mock
def test_naver_fetch_bodies_disabled_skips_extra_request(
    naver_source: Source,
    naver_json_response: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_naver_keys(monkeypatch)
    api_route = respx.get(NaverCollector.URL).mock(
        return_value=httpx.Response(200, json=naver_json_response),
    )
    body_route = respx.get(url__regex=r"^https://n\.news\.naver\.com/.*").mock(
        return_value=httpx.Response(200, text="<html></html>"),
    )

    collector = NaverCollector(fetch_bodies=False)
    try:
        results = collector.collect(naver_source)
    finally:
        collector.close()

    assert api_route.called
    assert body_route.call_count == 0
    assert all(r.raw_content is None for r in results)


@respx.mock
def test_naver_collect_request_sends_headers_and_params(
    naver_source: Source,
    naver_json_response: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_naver_keys(monkeypatch)
    api_route = respx.get(NaverCollector.URL).mock(
        return_value=httpx.Response(200, json=naver_json_response),
    )
    _mock_naver_body()

    collector = NaverCollector()
    try:
        collector.collect(naver_source)
    finally:
        collector.close()

    request = api_route.calls.last.request
    assert request.headers["X-Naver-Client-Id"] == "test-id"
    assert request.headers["X-Naver-Client-Secret"] == "test-secret"
    assert request.url.params["query"] == "AI"
    assert request.url.params["sort"] == "date"


@respx.mock
def test_naver_collect_handles_invalid_pubdate(
    naver_source: Source,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_naver_keys(monkeypatch)
    respx.get(NaverCollector.URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "title": "X",
                        "originallink": "https://x.example",
                        "link": "https://n.news.naver.com/mnews/article/001/x",
                        "description": "x",
                        "pubDate": "not a real date",
                    }
                ]
            },
        ),
    )
    _mock_naver_body()
    collector = NaverCollector()
    try:
        results = collector.collect(naver_source)
    finally:
        collector.close()
    assert len(results) == 1
    assert results[0].published_at is None


def test_naver_collect_requires_query(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_naver_keys(monkeypatch)
    source = Source(
        source_id="naver-empty",
        name="x",
        type="NAVER_API",
        content_track="expert_news",
        endpoint="https://openapi.naver.com/v1/search/news.json",
        query=None,
        priority="medium",
        trust_level="media",
        enabled=True,
        fetch_interval="daily",
        auth_required=True,
    )
    collector = NaverCollector()
    try:
        assert collector.collect(source) == []
    finally:
        collector.close()


def test_naver_collect_requires_credentials(
    naver_source: Source, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NAVER_CLIENT_ID", "")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "")
    from newsletter.core.config import get_settings

    get_settings.cache_clear()

    collector = NaverCollector()
    try:
        with pytest.raises(CollectorError, match="NAVER_CLIENT"):
            collector.collect(naver_source)
    finally:
        collector.close()


@respx.mock
def test_naver_collect_wraps_http_error(
    naver_source: Source, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings_with_naver_keys(monkeypatch)
    respx.get(NaverCollector.URL).mock(return_value=httpx.Response(500))
    collector = NaverCollector()
    try:
        with pytest.raises(CollectorError):
            collector.collect(naver_source)
    finally:
        collector.close()


@respx.mock
def test_naver_pubdate_parses_with_timezone(
    naver_source: Source, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings_with_naver_keys(monkeypatch)
    respx.get(NaverCollector.URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "title": "Date test",
                        "originallink": "https://d.example",
                        "link": "https://n.news.naver.com/mnews/article/001/d",
                        "description": "d",
                        "pubDate": "Mon, 12 May 2025 10:00:00 +0900",
                    }
                ]
            },
        ),
    )
    _mock_naver_body()
    collector = NaverCollector()
    try:
        results = collector.collect(naver_source)
    finally:
        collector.close()
    pub = results[0].published_at
    assert pub is not None
    assert pub.astimezone(UTC) == datetime(2025, 5, 12, 1, 0, tzinfo=UTC)
