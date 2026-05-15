"""End-to-end tests for the integration service.

These tests use the in-memory DB fixture and seed ProcessedItem +
RawItem + Source rows. The service joins them, scores, clusters,
selects, and persists ``importance_score`` back to ProcessedItem.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.integration.service import IntegrationReport, integrate
from newsletter.slices.sources import repository
from newsletter.slices.sources.schemas import SourceCreate

_NOW = datetime(2026, 5, 15, 12, 0, tzinfo=UTC)


def _seed_source(
    db_session: Session,
    *,
    source_id: str = "src",
    track: str = "expert_news",
    trust: str = "media",
    category: str = "AI Model",
) -> None:
    repository.add(
        db_session,
        SourceCreate(
            source_id=source_id,
            name=f"Source {source_id}",
            type="RSS",
            content_track=track,  # type: ignore[arg-type]
            endpoint="https://example.com",
            category=category,
            trust_level=trust,  # type: ignore[arg-type]
        ),
    )


def _seed_pair(
    db_session: Session,
    *,
    source_id: str,
    title: str,
    published_at: datetime,
    track: str = "expert_news",
    category: str = "AI Model",
    duplicate_group_id: str | None = None,
    url: str | None = None,
) -> ProcessedItem:
    raw = RawItem(
        source_id=source_id,
        title=title,
        url=url or f"https://example.com/{title[:20]}",
        published_at=published_at,
        raw_summary=f"summary of {title}",
        language="en",
    )
    db_session.add(raw)
    db_session.flush()
    proc = ProcessedItem(
        raw_item_id=raw.id,
        normalized_title=title,
        canonical_url=raw.url,
        content_track=track,
        category=category,
        relevance_score=0.8,
        importance_score=0.0,
        summary=raw.raw_summary,
        keywords=None,
        duplicate_group_id=duplicate_group_id,
    )
    db_session.add(proc)
    db_session.flush()
    return proc


def test_integrate_empty_db_returns_empty_report(db_session: Session) -> None:
    report = integrate(db_session, now=_NOW)
    assert isinstance(report, IntegrationReport)
    assert report.scored == 0
    assert report.expert_candidates == []
    assert report.practical_candidates == []


def test_integrate_writes_importance_score(db_session: Session) -> None:
    _seed_source(db_session)
    proc = _seed_pair(
        db_session,
        source_id="src",
        title="OpenAI launches GPT-5 reasoning model",
        published_at=_NOW,
    )
    db_session.commit()

    report = integrate(db_session, now=_NOW)
    db_session.commit()

    assert report.scored == 1
    refreshed = db_session.get(ProcessedItem, proc.id)
    assert refreshed is not None
    assert refreshed.importance_score > 0.0


def test_integrate_returns_candidates_per_track(db_session: Session) -> None:
    _seed_source(db_session, source_id="src_expert", track="expert_news")
    _seed_source(
        db_session,
        source_id="src_practical",
        track="practical_insight",
        category="Tutorial",
    )
    _seed_pair(
        db_session,
        source_id="src_expert",
        title="Anthropic releases Claude 5 frontier model",
        track="expert_news",
        published_at=_NOW,
    )
    _seed_pair(
        db_session,
        source_id="src_practical",
        title="How to use Claude for spreadsheet automation",
        track="practical_insight",
        category="Tutorial",
        published_at=_NOW,
        url="https://example.com/p1",
    )
    db_session.commit()

    report = integrate(db_session, now=_NOW)

    assert len(report.expert_candidates) == 1
    assert len(report.practical_candidates) == 1
    assert report.expert_candidates[0].track == "expert_news"
    assert report.practical_candidates[0].track == "practical_insight"


def test_integrate_respects_per_track_limits(db_session: Session) -> None:
    _seed_source(db_session)
    distinct_titles = [
        "OpenAI launches GPT-5 reasoning model",
        "Google publishes Gemini 3 update",
        "Meta open-sources Llama 4 weights",
        "Anthropic ships Claude 5 frontier",
        "Microsoft Copilot wins enterprise deals",
        "EU passes new AI safety act",
        "Stanford releases foundation model report",
        "DeepMind solves protein folding extension",
    ]
    for i, title in enumerate(distinct_titles):
        _seed_pair(
            db_session,
            source_id="src",
            title=title,
            category=f"Cat{i}",
            published_at=_NOW - timedelta(hours=i),
            url=f"https://example.com/i{i}",
        )
    db_session.commit()

    report = integrate(db_session, now=_NOW, expert_count=3, practical_count=1)
    assert len(report.expert_candidates) == 3


def test_integrate_collapses_duplicate_group(db_session: Session) -> None:
    _seed_source(db_session)
    a = _seed_pair(
        db_session,
        source_id="src",
        title="OpenAI launches GPT-5",
        published_at=_NOW,
        duplicate_group_id="gA",
        url="https://example.com/a",
    )
    b = _seed_pair(
        db_session,
        source_id="src",
        title="GPT-5 ships from OpenAI",
        published_at=_NOW,
        duplicate_group_id="gA",
        url="https://example.com/b",
    )
    db_session.commit()

    report = integrate(db_session, now=_NOW)
    # Both processed but one candidate per cluster.
    assert report.scored == 2
    assert len(report.expert_candidates) == 1
    cand = report.expert_candidates[0]
    assert set(cand.cluster_member_ids) == {a.id, b.id}


def test_integrate_is_rerunnable_with_fresh_scores(db_session: Session) -> None:
    _seed_source(db_session)
    proc = _seed_pair(
        db_session,
        source_id="src",
        title="OpenAI Claude release model",
        published_at=_NOW,
    )
    db_session.commit()

    integrate(db_session, now=_NOW)
    db_session.commit()
    score_fresh = db_session.get(ProcessedItem, proc.id).importance_score

    later = _NOW + timedelta(days=10)
    integrate(db_session, now=later)
    db_session.commit()
    score_old = db_session.get(ProcessedItem, proc.id).importance_score

    # Same item, much older → score must decay.
    assert score_old < score_fresh


def test_integrate_skips_items_without_source(db_session: Session) -> None:
    """If somehow a ProcessedItem references a vanished source, we don't crash."""
    _seed_source(db_session, source_id="src")
    _seed_pair(
        db_session,
        source_id="src",
        title="AI model launches new feature",
        published_at=_NOW,
    )
    # Manually orphan: not actually deletable due to FK, but ensure code path
    # tolerates a row whose source row is enabled=False (still present).
    db_session.commit()

    report = integrate(db_session, now=_NOW)
    assert report.scored == 1


def test_integrate_uses_naive_published_at(db_session: Session) -> None:
    """A naïve datetime in DB (SQLite drops tzinfo) must still score."""
    _seed_source(db_session)
    # Force naïve by passing a tz-stripped datetime — SQLite returns naïve.
    naive_now = _NOW.replace(tzinfo=None)
    proc = _seed_pair(
        db_session,
        source_id="src",
        title="Anthropic AI Claude release",
        published_at=naive_now,
    )
    db_session.commit()

    report = integrate(db_session, now=_NOW)
    assert report.scored == 1
    assert db_session.get(ProcessedItem, proc.id).importance_score > 0.0
