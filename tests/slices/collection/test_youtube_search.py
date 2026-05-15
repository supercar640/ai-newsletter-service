"""YouTubeSearchCollector — search + top-N selection + STT."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from newsletter.core.run_context import RunContext
from newsletter.models.source import Source
from newsletter.slices.collection.base import CollectorError
from newsletter.slices.collection.stt import TranscriptionResult
from newsletter.slices.collection.youtube_search import YouTubeSearchCollector
from newsletter.slices.sources import repository
from newsletter.slices.sources.schemas import SourceCreate


@pytest.fixture
def search_source(db_session) -> Source:  # type: ignore[no-untyped-def]
    return repository.add(
        db_session,
        SourceCreate(
            source_id="yt-search-test",
            name="YouTube search test",
            type="YOUTUBE_SEARCH",
            content_track="practical_insight",
            endpoint="https://www.googleapis.com/youtube/v3/search",
            query="AI 활용법",
            language="ko",
        ),
    )


def _settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    key: str = "yt-test",
    top_n: int = 3,
    stt: str = "0",
) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", key)
    monkeypatch.setenv("YOUTUBE_SEARCH_TOP_N", str(top_n))
    monkeypatch.setenv("YOUTUBE_STT_ENABLED", stt)
    from newsletter.core.config import get_settings

    get_settings.cache_clear()


def _search_response(*video_ids: str) -> dict:
    return {
        "items": [
            {
                "id": {"kind": "youtube#video", "videoId": vid},
                "snippet": {"title": "t", "channelTitle": "ch"},
            }
            for vid in video_ids
        ]
    }


def _videos_response(*entries: tuple[str, int, str]) -> dict:
    """Each entry is (video_id, view_count, description)."""
    return {
        "items": [
            {
                "id": vid,
                "snippet": {
                    "title": f"Title {vid}",
                    "description": desc,
                    "channelTitle": "ch",
                    "publishedAt": "2025-05-12T09:00:00Z",
                },
                "statistics": {"viewCount": str(views)},
            }
            for vid, views, desc in entries
        ]
    }


def test_youtube_search_requires_api_key(
    search_source: Source, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(monkeypatch, key="")
    collector = YouTubeSearchCollector()
    try:
        with pytest.raises(CollectorError, match="YOUTUBE_API_KEY"):
            collector.collect(search_source)
    finally:
        collector.close()


def test_youtube_search_requires_query(
    db_session,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[no-untyped-def]
) -> None:
    _settings(monkeypatch)
    source = Source(
        source_id="yt-empty",
        name="x",
        type="YOUTUBE_SEARCH",
        content_track="practical_insight",
        endpoint="https://www.googleapis.com/youtube/v3/search",
        query=None,
        priority="medium",
        trust_level="community",
        enabled=True,
        fetch_interval="daily",
        auth_required=False,
    )
    collector = YouTubeSearchCollector()
    try:
        with pytest.raises(CollectorError, match="no query"):
            collector.collect(source)
    finally:
        collector.close()


@respx.mock
def test_youtube_search_sorts_by_view_count_and_keeps_top_n(
    search_source: Source, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(monkeypatch, top_n=2)
    respx.get(YouTubeSearchCollector.SEARCH_URL).mock(
        return_value=httpx.Response(
            200, json=_search_response("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc")
        ),
    )
    respx.get(YouTubeSearchCollector.VIDEOS_URL).mock(
        return_value=httpx.Response(
            200,
            json=_videos_response(
                ("aaaaaaaaaaa", 100, "low"),
                ("bbbbbbbbbbb", 99999, "highest"),
                ("ccccccccccc", 5000, "middle"),
            ),
        ),
    )

    collector = YouTubeSearchCollector()
    try:
        results = collector.collect(search_source)
    finally:
        collector.close()

    assert len(results) == 2
    # Sorted by view count desc → bbbbbbbbbbb (99999) > ccccccccccc (5000) > aaaaaaaaaaa (100)
    assert results[0].url == "https://www.youtube.com/watch?v=bbbbbbbbbbb"
    assert results[1].url == "https://www.youtube.com/watch?v=ccccccccccc"


@respx.mock
def test_youtube_search_sends_query_and_key(
    search_source: Source, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(monkeypatch, key="my-key")
    search_route = respx.get(YouTubeSearchCollector.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_search_response("aaaaaaaaaaa")),
    )
    respx.get(YouTubeSearchCollector.VIDEOS_URL).mock(
        return_value=httpx.Response(200, json=_videos_response(("aaaaaaaaaaa", 1, "x"))),
    )

    collector = YouTubeSearchCollector()
    try:
        collector.collect(search_source)
    finally:
        collector.close()

    req = search_route.calls.last.request
    assert req.url.params["q"] == "AI 활용법"
    assert req.url.params["key"] == "my-key"
    assert req.url.params["type"] == "video"


@respx.mock
def test_youtube_search_empty_returns_empty(
    search_source: Source, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(monkeypatch)
    respx.get(YouTubeSearchCollector.SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"items": []}),
    )

    collector = YouTubeSearchCollector()
    try:
        results = collector.collect(search_source)
    finally:
        collector.close()
    assert results == []


@respx.mock
def test_youtube_search_with_stt_uses_transcript(
    search_source: Source,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings(monkeypatch, stt="1", top_n=1)
    respx.get(YouTubeSearchCollector.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_search_response("aaaaaaaaaaa")),
    )
    respx.get(YouTubeSearchCollector.VIDEOS_URL).mock(
        return_value=httpx.Response(
            200, json=_videos_response(("aaaaaaaaaaa", 1, "API description"))
        ),
    )

    # Stub the STT pipeline so the test doesn't touch yt-dlp / whisper.
    fake_transcript = "이것은 영상의 전사 텍스트입니다."
    from newsletter.slices.collection import youtube_search as ys_mod

    def _stub(video_url: str, video_id: str, dest_dir: Path) -> TranscriptionResult:
        audio = dest_dir / f"{video_id}.m4a"
        audio.write_bytes(b"\x00")
        transcript = dest_dir / f"{video_id}.txt"
        transcript.write_text(fake_transcript, encoding="utf-8")
        return TranscriptionResult(
            audio_path=audio,
            transcript_path=transcript,
            text=fake_transcript,
            language="ko",
            duration_seconds=12.34,
        )

    monkeypatch.setattr(ys_mod, "download_and_transcribe", _stub)

    run_ctx = RunContext.new(tmp_path, run_id="rid")
    collector = YouTubeSearchCollector(run_context=run_ctx)
    try:
        results = collector.collect(search_source)
    finally:
        collector.close()

    assert len(results) == 1
    assert results[0].raw_content == fake_transcript
    # Artifacts on disk
    assert (run_ctx.path / "youtube" / "yt-search-test" / "aaaaaaaaaaa.txt").exists()


@respx.mock
def test_youtube_search_stt_failure_falls_back_to_description(
    search_source: Source,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings(monkeypatch, stt="1", top_n=1)
    respx.get(YouTubeSearchCollector.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=_search_response("aaaaaaaaaaa")),
    )
    respx.get(YouTubeSearchCollector.VIDEOS_URL).mock(
        return_value=httpx.Response(
            200, json=_videos_response(("aaaaaaaaaaa", 1, "Description fallback"))
        ),
    )

    from newsletter.slices.collection import stt as stt_mod
    from newsletter.slices.collection import youtube_search as ys_mod

    def _fail(*args, **kwargs):
        raise stt_mod.STTError("boom")

    monkeypatch.setattr(ys_mod, "download_and_transcribe", _fail)

    run_ctx = RunContext.new(tmp_path, run_id="rid")
    collector = YouTubeSearchCollector(run_context=run_ctx)
    try:
        results = collector.collect(search_source)
    finally:
        collector.close()

    assert len(results) == 1
    assert results[0].raw_content == "Description fallback"
