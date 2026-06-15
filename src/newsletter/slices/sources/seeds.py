"""Initial Source Registry seeds.

Idempotent: re-running ``newsletter sources seed`` updates existing rows
in place rather than failing.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from newsletter.slices.sources import repository
from newsletter.slices.sources.schemas import SourceCreate

SEED_SOURCES: list[SourceCreate] = [
    SourceCreate(
        source_id="naver-ai",
        name="Naver News — AI",
        type="NAVER_API",
        content_track="both",
        endpoint="https://openapi.naver.com/v1/search/news.json",
        query="AI",
        language="ko",
        region="KR",
        category="AI General",
        priority="high",
        trust_level="media",
        fetch_interval="daily",
        auth_required=True,
        owner="admin",
    ),
    SourceCreate(
        source_id="techcrunch-ai",
        name="TechCrunch — AI",
        type="RSS",
        content_track="expert_news",
        endpoint="https://techcrunch.com/category/artificial-intelligence/feed/",
        language="en",
        region="US",
        category="Industry",
        priority="high",
        trust_level="media",
        fetch_interval="daily",
        owner="admin",
    ),
    SourceCreate(
        source_id="openai-blog",
        name="OpenAI Blog",
        type="RSS",
        content_track="expert_news",
        # blog/rss.xml redirects here; both return the FULL archive (~1000 items).
        endpoint="https://openai.com/news/rss.xml",
        language="en",
        region="Global",
        category="AI Model",
        priority="high",
        trust_level="official",
        fetch_interval="daily",
        # Disabled: feed dumps the entire archive, swamping the pipeline. Re-enable
        # once collection has a recency gate (max-age / max-items per fetch).
        enabled=False,
        rate_limit_note="RSS returns full archive (~1000 items); needs a recency gate before re-enabling.",
        owner="admin",
    ),
    SourceCreate(
        source_id="mit-tech-review-ai",
        name="MIT Technology Review — AI",
        type="RSS",
        content_track="expert_news",
        endpoint="https://www.technologyreview.com/feed/",
        language="en",
        region="US",
        category="Research",
        priority="medium",
        trust_level="media",
        fetch_interval="daily",
        owner="admin",
    ),
    SourceCreate(
        source_id="youtube-anthropic",
        name="YouTube — Anthropic",
        type="YOUTUBE_RSS",
        content_track="practical_insight",
        endpoint=("https://www.youtube.com/feeds/videos.xml?channel_id=UCrDwWp7EBBv4NwvScIpBDOA"),
        language="en",
        region="Global",
        category="Prompting",
        audience_level="beginner",
        priority="medium",
        trust_level="official",
        fetch_interval="weekly",
        owner="admin",
    ),
    # --- YOUTUBE_SEARCH sources (Iteration 2.5) ----------------------------
    # For each keyword the YouTube Data API is searched, the top N videos
    # by view count are kept, audio is downloaded via yt-dlp, and
    # faster-whisper transcribes them. Transcripts land in RawItem.raw_content
    # and on disk under data/runs/<id>/youtube/<source-id>/.
    SourceCreate(
        source_id="yt-search-ai-howto",
        name="YouTube 검색 — AI 활용법",
        type="YOUTUBE_SEARCH",
        content_track="practical_insight",
        endpoint="https://www.googleapis.com/youtube/v3/search",
        query="AI 활용법",
        language="ko",
        region="KR",
        category="Productivity",
        audience_level="beginner",
        priority="high",
        trust_level="community",
        fetch_interval="daily",
        owner="admin",
    ),
    SourceCreate(
        source_id="yt-search-chatgpt-howto",
        name="YouTube 검색 — ChatGPT 사용법",
        type="YOUTUBE_SEARCH",
        content_track="practical_insight",
        endpoint="https://www.googleapis.com/youtube/v3/search",
        query="ChatGPT 사용법",
        language="ko",
        region="KR",
        category="Prompting",
        audience_level="beginner",
        priority="high",
        trust_level="community",
        fetch_interval="daily",
        owner="admin",
    ),
    SourceCreate(
        source_id="yt-search-ai-automation",
        name="YouTube 검색 — AI 자동화",
        type="YOUTUBE_SEARCH",
        content_track="practical_insight",
        endpoint="https://www.googleapis.com/youtube/v3/search",
        query="AI 자동화",
        language="ko",
        region="KR",
        category="Workflow Automation",
        audience_level="intermediate",
        priority="high",
        trust_level="community",
        fetch_interval="daily",
        owner="admin",
    ),
]


def seed(session: Session) -> tuple[int, int]:
    """Apply seed data. Returns ``(created, updated)``."""
    created = updated = 0
    for payload in SEED_SOURCES:
        _, was_created = repository.upsert(session, payload)
        if was_created:
            created += 1
        else:
            updated += 1
    return created, updated
