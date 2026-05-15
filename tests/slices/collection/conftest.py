"""Fixtures shared by collection slice tests."""

from __future__ import annotations

import textwrap

import pytest

from newsletter.models.source import Source
from newsletter.slices.sources import repository
from newsletter.slices.sources.schemas import SourceCreate


@pytest.fixture
def naver_source(db_session) -> Source:
    return repository.add(
        db_session,
        SourceCreate(
            source_id="naver-ai",
            name="Naver AI",
            type="NAVER_API",
            content_track="expert_news",
            endpoint="https://openapi.naver.com/v1/search/news.json",
            query="AI",
            language="ko",
        ),
    )


@pytest.fixture
def rss_source(db_session) -> Source:
    return repository.add(
        db_session,
        SourceCreate(
            source_id="techcrunch-ai",
            name="TechCrunch AI",
            type="RSS",
            content_track="expert_news",
            endpoint="https://example.com/rss.xml",
            language="en",
        ),
    )


@pytest.fixture
def youtube_source(db_session) -> Source:
    return repository.add(
        db_session,
        SourceCreate(
            source_id="youtube-anthropic",
            name="YouTube Anthropic",
            type="YOUTUBE_RSS",
            content_track="practical_insight",
            endpoint="https://www.youtube.com/feeds/videos.xml?channel_id=UC123",
            language="en",
        ),
    )


@pytest.fixture
def naver_json_response() -> dict:
    """Two Naver-hosted items. Item 2 has empty originallink → link is used as URL."""
    return {
        "lastBuildDate": "Mon, 12 May 2025 10:30:00 +0900",
        "total": 2,
        "start": 1,
        "display": 2,
        "items": [
            {
                "title": "OpenAI <b>GPT-5</b> &quot;출시&quot; 임박",
                "originallink": "https://news.example.com/openai-gpt5",
                "link": "https://n.news.naver.com/mnews/article/001/123",
                "description": "OpenAI가 <b>GPT-5</b> 모델을 공개했다.",
                "pubDate": "Mon, 12 May 2025 10:00:00 +0900",
            },
            {
                "title": "Anthropic Claude 신모델",
                "originallink": "",
                "link": "https://n.news.naver.com/mnews/article/002/456",
                "description": "Anthropic이 Claude 새 버전을 발표했다.",
                "pubDate": "Sun, 11 May 2025 22:15:00 +0900",
            },
        ],
    }


@pytest.fixture
def naver_mixed_links_response() -> dict:
    """Mix of Naver and non-Naver hosted links to exercise the filter."""
    return {
        "items": [
            {
                "title": "kept",
                "originallink": "https://news.example.com/keep",
                "link": "https://n.news.naver.com/mnews/article/001/keep",
                "description": "kept",
                "pubDate": "Mon, 12 May 2025 10:00:00 +0900",
            },
            {
                "title": "dropped because non-naver",
                "originallink": "https://other.example.com/drop",
                "link": "https://other.example.com/drop",
                "description": "dropped",
                "pubDate": "Mon, 12 May 2025 09:00:00 +0900",
            },
            {
                "title": "dropped because empty link",
                "originallink": "https://orig.example.com/drop2",
                "link": "",
                "description": "dropped",
                "pubDate": "Mon, 12 May 2025 09:00:00 +0900",
            },
        ]
    }


@pytest.fixture
def naver_article_html() -> str:
    """Realistic-enough Naver article page with a #dic_area body."""
    return """<!DOCTYPE html><html><head><title>x</title>
        <script>var a = 1;</script>
        <style>.x{}</style>
        </head><body>
        <header>Top nav</header>
        <article id="dic_area">
            <p>첫째 문단입니다.</p>
            <p>둘째 문단에는    공백   이 많습니다.</p>
            <p>마지막 문단.</p>
        </article>
        <footer>copyright</footer>
        </body></html>"""


@pytest.fixture
def rss_feed_xml() -> bytes:
    return textwrap.dedent(
        """\
        <?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>TechCrunch AI</title>
            <link>https://example.com</link>
            <description>AI news</description>
            <item>
              <title>OpenAI announces o-series</title>
              <link>https://example.com/openai-o-series</link>
              <description>OpenAI shares a new line of reasoning models.</description>
              <pubDate>Mon, 12 May 2025 09:00:00 GMT</pubDate>
              <author>jane@example.com (Jane Doe)</author>
            </item>
            <item>
              <title>Anthropic Sonnet update</title>
              <link>https://example.com/anthropic-sonnet</link>
              <description>Anthropic ships a Claude Sonnet revision.</description>
              <pubDate>Sun, 11 May 2025 18:30:00 GMT</pubDate>
            </item>
          </channel>
        </rss>
        """
    ).encode("utf-8")


@pytest.fixture
def youtube_feed_xml() -> bytes:
    """Real YouTube video ids are exactly 11 characters."""
    return textwrap.dedent(
        """\
        <?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:yt="http://www.youtube.com/xml/schemas/2015"
              xmlns:media="http://search.yahoo.com/mrss/">
          <title>Anthropic</title>
          <entry>
            <id>yt:video:abcABC12345</id>
            <yt:videoId>abcABC12345</yt:videoId>
            <title>Building agents with Claude</title>
            <link rel="alternate" href="https://www.youtube.com/watch?v=abcABC12345"/>
            <author><name>Anthropic</name></author>
            <published>2025-05-12T09:00:00+00:00</published>
            <updated>2025-05-12T09:00:00+00:00</updated>
            <media:group>
              <media:description>How to build coding agents with Claude.</media:description>
            </media:group>
          </entry>
          <entry>
            <id>yt:video:defDEF98765</id>
            <yt:videoId>defDEF98765</yt:videoId>
            <title>Tool use deep dive</title>
            <link rel="alternate" href="https://www.youtube.com/watch?v=defDEF98765"/>
            <author><name>Anthropic</name></author>
            <published>2025-05-10T12:30:00+00:00</published>
            <updated>2025-05-10T12:30:00+00:00</updated>
          </entry>
        </feed>
        """
    ).encode("utf-8")
