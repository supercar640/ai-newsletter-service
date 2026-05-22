"""competitors.service — window query + alias detection."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.competitors import repository
from newsletter.slices.competitors.schemas import CompetitorCreate
from newsletter.slices.competitors.service import analyze_competitors
from newsletter.slices.sources import repository as sources_repo
from newsletter.slices.sources.schemas import SourceCreate

_UNTIL = date(2026, 5, 22)  # exclusive upper bound used in tests


def _seed_source(db_session: Session) -> None:
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


def _seed_item(
    db_session: Session,
    *,
    title: str,
    summary: str,
    importance: float,
    published_at: datetime | None,
    created_at: datetime | None = None,
) -> None:
    raw = RawItem(
        source_id="src",
        title=title,
        url=f"https://example.com/{title[:24]}-{published_at}-{created_at}",
        published_at=published_at,
        raw_summary=summary,
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    kwargs = {}
    if created_at is not None:
        kwargs["created_at"] = created_at
    proc = ProcessedItem(
        raw_item_id=raw.id,
        normalized_title=title,
        canonical_url=raw.url,
        content_track="expert_news",
        category="AI Model",
        relevance_score=0.9,
        importance_score=importance,
        summary=summary,
        keywords=None,
        duplicate_group_id=None,
        **kwargs,
    )
    db_session.add(proc)
    db_session.flush()


def test_counts_and_window_filtering(db_session: Session):
    _seed_source(db_session)
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai", "gpt"]))
    # in window
    _seed_item(
        db_session,
        title="OpenAI ships GPT-5",
        summary="big day",
        importance=2.0,
        published_at=datetime(2026, 5, 20, 9, 0),
    )
    # outside window (too old)
    _seed_item(
        db_session,
        title="OpenAI old news",
        summary="last month",
        importance=1.0,
        published_at=datetime(2026, 4, 1, 9, 0),
    )
    db_session.commit()

    report = analyze_competitors(db_session, days=7, until=_UNTIL)
    assert report.total_items == 1  # only the in-window item scanned
    assert len(report.competitors) == 1
    mentions = report.competitors[0]
    assert mentions.name == "OpenAI"
    assert mentions.count == 1
    assert mentions.headlines[0].title == "OpenAI ships GPT-5"


def test_multiple_competitors_attributed(db_session: Session):
    _seed_source(db_session)
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai"]))
    repository.add(db_session, CompetitorCreate(name="Google", aliases=["gemini"]))
    _seed_item(
        db_session,
        title="OpenAI and Gemini both ship",
        summary="rivalry",
        importance=3.0,
        published_at=datetime(2026, 5, 20, 9, 0),
    )
    db_session.commit()

    report = analyze_competitors(db_session, days=7, until=_UNTIL)
    by_name = {m.name: m for m in report.competitors}
    assert by_name["OpenAI"].count == 1
    assert by_name["Google"].count == 1
    # ordering: count desc then name asc -> tie broken by name
    assert [m.name for m in report.competitors] == ["Google", "OpenAI"]


def test_disabled_competitor_excluded(db_session: Session):
    _seed_source(db_session)
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai"], enabled=False))
    _seed_item(
        db_session,
        title="OpenAI ships",
        summary="x",
        importance=1.0,
        published_at=datetime(2026, 5, 20, 9, 0),
    )
    db_session.commit()
    report = analyze_competitors(db_session, days=7, until=_UNTIL)
    assert report.competitors == []


def test_published_at_null_falls_back_to_created_at(db_session: Session):
    _seed_source(db_session)
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai"]))
    _seed_item(
        db_session,
        title="OpenAI fallback",
        summary="x",
        importance=1.0,
        published_at=None,
        created_at=datetime(2026, 5, 20, 9, 0),
    )
    db_session.commit()
    report = analyze_competitors(db_session, days=7, until=_UNTIL)
    assert report.total_items == 1
    assert report.competitors[0].count == 1


def test_zero_count_competitor_appears_as_watchlist(db_session: Session):
    _seed_source(db_session)
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai"]))
    repository.add(db_session, CompetitorCreate(name="Cohere", aliases=["cohere"]))
    _seed_item(
        db_session,
        title="OpenAI ships",
        summary="x",
        importance=1.0,
        published_at=datetime(2026, 5, 20, 9, 0),
    )
    db_session.commit()
    report = analyze_competitors(db_session, days=7, until=_UNTIL)
    by_name = {m.name: m for m in report.competitors}
    # Cohere is never mentioned but still appears (watch-list), count 0
    assert by_name["Cohere"].count == 0
    assert by_name["Cohere"].headlines == []
    # ordering: OpenAI (count 1) before Cohere (count 0)
    assert [m.name for m in report.competitors] == ["OpenAI", "Cohere"]


def test_headlines_truncated_to_top_k_in_importance_order(db_session: Session):
    _seed_source(db_session)
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai"]))
    for i in range(5):
        _seed_item(
            db_session,
            title=f"OpenAI story {i}",
            summary="x",
            importance=float(i),  # 0..4
            published_at=datetime(2026, 5, 20, 9, 0),
        )
    db_session.commit()
    report = analyze_competitors(db_session, days=7, until=_UNTIL, top_k=2)
    mentions = report.competitors[0]
    assert mentions.count == 5  # count is NOT truncated
    assert len(mentions.headlines) == 2  # headlines truncated to top_k
    # highest importance first
    assert [h.importance for h in mentions.headlines] == [4.0, 3.0]


def test_explicit_since_overrides_days(db_session: Session):
    _seed_source(db_session)
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai"]))
    # item on 2026-05-10 — inside a 'since=2026-05-08' window but outside default days=7
    _seed_item(
        db_session,
        title="OpenAI early",
        summary="x",
        importance=1.0,
        published_at=datetime(2026, 5, 10, 9, 0),
    )
    db_session.commit()
    # default days=7 from until 05-22 -> since 05-15: item excluded
    narrow = analyze_competitors(db_session, days=7, until=_UNTIL)
    assert narrow.competitors[0].count == 0
    # explicit since=05-08 -> item included
    wide = analyze_competitors(db_session, since=date(2026, 5, 8), until=_UNTIL)
    assert wide.competitors[0].count == 1


def test_empty_registry_returns_empty_report(db_session: Session):
    _seed_source(db_session)
    _seed_item(
        db_session,
        title="OpenAI ships",
        summary="x",
        importance=1.0,
        published_at=datetime(2026, 5, 20, 9, 0),
    )
    db_session.commit()
    report = analyze_competitors(db_session, days=7, until=_UNTIL)
    assert report.competitors == []
    assert report.total_items == 1  # item still scanned
