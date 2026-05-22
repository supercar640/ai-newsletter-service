"""site.builder — assembles every report into linked pages."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from newsletter.core.embeddings import DisabledEmbeddingClient
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.site.builder import build_index_markdown, build_site_pages
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate


def _seed(db_session: Session) -> None:
    sources_repo.add(
        db_session,
        SourceCreate(
            source_id="src",
            name="src",
            type="RSS",
            content_track="expert_news",  # type: ignore[arg-type]
            endpoint="https://example.com",
            category="AI Model",
            trust_level="media",  # type: ignore[arg-type]
        ),
    )
    raw = RawItem(
        source_id="src",
        title="OpenAI ships GPT-5",
        url="https://example.com/x",
        published_at=datetime(2026, 5, 20, 9, 0),
        collected_at=datetime(2026, 5, 20, 9, 0),
        raw_summary="news",
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    db_session.add(
        ProcessedItem(
            raw_item_id=raw.id,
            normalized_title="OpenAI ships GPT-5",
            canonical_url="https://example.com/x",
            content_track="expert_news",
            category="AI Model",
            relevance_score=0.9,
            importance_score=1.0,
            summary="news",
        )
    )
    db_session.commit()


def test_build_site_pages_has_all_reports(db_session: Session):
    _seed(db_session)
    pages = build_site_pages(db_session, embed_client=DisabledEmbeddingClient())
    slugs = [p.slug for p in pages]
    assert slugs == ["trends", "competitors", "monthly", "dashboard", "departments"]
    for p in pages:
        assert p.markdown.strip()
        assert p.title


def test_build_index_markdown_links_each_page(db_session: Session):
    _seed(db_session)
    pages = build_site_pages(db_session, embed_client=DisabledEmbeddingClient())
    md = build_index_markdown(pages, generated_at=datetime(2026, 5, 22, 10, 0))
    assert "# AI 인텔리전스 리포트" in md
    assert "2026-05-22 10:00" in md
    for p in pages:
        assert f"({p.slug}.html)" in md
