"""CLI integration for ``newsletter collect``."""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlalchemy import select
from typer.testing import CliRunner

from newsletter.cli import app
from newsletter.core import db as core_db
from newsletter.core.config import Settings, get_settings
from newsletter.models.raw_item import RawItem
from newsletter.slices.sources import repository, seeds
from newsletter.slices.sources.schemas import SourceCreate

_NAVER_URL = "https://openapi.naver.com/v1/search/news.json"
_NAVER_BODY = {
    "items": [
        {
            "title": "<b>AI</b> 모델 업데이트",
            "originallink": "https://news.example.com/ai",
            "link": "https://n.news.naver.com/mnews/article/001/ai",
            "description": "내용",
            "pubDate": "Mon, 12 May 2025 10:00:00 +0900",
        }
    ]
}
_NAVER_ARTICLE_HTML = (
    "<html><body><article id='dic_area'>전문 본문 내용입니다.</article></body></html>"
)

_FEED_XML = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <title>x</title><link>https://x</link><description>x</description>
      <item><title>Item One</title><link>https://feed.example/1</link>
        <description>one</description>
        <pubDate>Mon, 12 May 2025 09:00:00 GMT</pubDate></item>
    </channel></rss>"""


@pytest.fixture
def runner(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NAVER_CLIENT_ID", "test-id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "test-secret")
    get_settings.cache_clear()
    del settings  # fixture is consumed for env-var side-effects only

    core_db.reset_engine_for_tests()
    import newsletter.models  # noqa: F401 — register models on Base.metadata

    engine = core_db.get_engine()
    core_db.Base.metadata.create_all(engine)
    yield CliRunner()
    core_db.Base.metadata.drop_all(engine)
    core_db.reset_engine_for_tests()


def _mock_seed_endpoints() -> None:
    """Mock every endpoint used by the seed data."""
    respx.get(_NAVER_URL).mock(return_value=httpx.Response(200, json=_NAVER_BODY))
    # Naver also fetches the article page for body extraction.
    respx.get(url__regex=r"^https://n\.news\.naver\.com/.*").mock(
        return_value=httpx.Response(200, text=_NAVER_ARTICLE_HTML),
    )
    respx.get("https://techcrunch.com/category/artificial-intelligence/feed/").mock(
        return_value=httpx.Response(200, content=_FEED_XML),
    )
    respx.get("https://openai.com/blog/rss.xml").mock(
        return_value=httpx.Response(200, content=_FEED_XML),
    )
    respx.get("https://www.technologyreview.com/feed/").mock(
        return_value=httpx.Response(200, content=_FEED_XML),
    )
    respx.get(url__regex=r"^https://www\.youtube\.com/feeds/videos\.xml.*").mock(
        return_value=httpx.Response(200, content=_FEED_XML),
    )


@respx.mock
def test_collect_runs_against_seeded_sources(runner: CliRunner) -> None:
    with core_db.session_scope() as session:
        seeds.seed(session)
    _mock_seed_endpoints()

    result = runner.invoke(app, ["collect"])
    assert result.exit_code == 0, result.output
    assert "Total:" in result.output
    assert "0 errors" in result.output

    with core_db.session_scope() as session:
        rows = session.scalars(select(RawItem)).all()
    # 1 Naver + 4 RSS-style sources, each with 1 mocked item = 5
    assert len(rows) == 5


def test_collect_with_no_sources_prints_message(runner: CliRunner) -> None:
    result = runner.invoke(app, ["collect"])
    assert result.exit_code == 0
    assert "no enabled sources" in result.output


@respx.mock
def test_collect_filters_by_source_id(runner: CliRunner) -> None:
    with core_db.session_scope() as session:
        seeds.seed(session)
    _mock_seed_endpoints()

    result = runner.invoke(app, ["collect", "--source-id", "openai-blog"])
    assert result.exit_code == 0, result.output
    body_lines = [ln for ln in result.output.splitlines() if ln.startswith("openai-blog")]
    assert len(body_lines) == 1
    assert "techcrunch-ai" not in result.output


@respx.mock
def test_collect_exits_nonzero_when_any_source_errors(runner: CliRunner) -> None:
    with core_db.session_scope() as session:
        repository.add(
            session,
            SourceCreate(
                source_id="rss-fail",
                name="Failing",
                type="RSS",
                content_track="expert_news",
                endpoint="https://broken.example/rss.xml",
            ),
        )
    respx.get("https://broken.example/rss.xml").mock(return_value=httpx.Response(500))

    result = runner.invoke(app, ["collect"])
    assert result.exit_code == 1
    assert "ERR" in result.output
