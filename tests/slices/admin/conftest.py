"""Shared admin-slice fixtures: helpers for seeding issues + items."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime

import pytest

from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.models.source import Source


@pytest.fixture
def make_source(db_session) -> Callable[..., Source]:
    counter = {"n": 0}

    def _make(
        source_id: str | None = None, trust_level: str = "media", name: str = "Test Source"
    ) -> Source:
        counter["n"] += 1
        sid = source_id or f"src{counter['n']}"
        src = Source(
            source_id=sid,
            name=name,
            type="RSS",
            content_track="expert_news",
            endpoint=f"http://example.com/{sid}",
            priority="medium",
            trust_level=trust_level,
            fetch_interval="daily",
        )
        db_session.add(src)
        db_session.flush()
        return src

    return _make


@pytest.fixture
def make_processed_item(db_session, make_source) -> Callable[..., ProcessedItem]:
    counter = {"n": 0}

    def _make(
        title: str = "Item",
        track: str = "expert_news",
        importance: float = 0.5,
        category: str | None = None,
        url: str | None = None,
        source: Source | None = None,
    ) -> ProcessedItem:
        counter["n"] += 1
        src = source or make_source()
        item_url = url or f"http://example.com/item-{counter['n']}"
        raw = RawItem(
            source_id=src.source_id,
            title=title,
            url=item_url,
            collected_at=datetime.now(UTC),
        )
        db_session.add(raw)
        db_session.flush()
        proc = ProcessedItem(
            raw_item_id=raw.id,
            normalized_title=title,
            canonical_url=item_url,
            content_track=track,
            category=category,
            importance_score=importance,
        )
        db_session.add(proc)
        db_session.flush()
        return proc

    return _make


@pytest.fixture
def make_issue(db_session) -> Callable[..., NewsletterIssue]:
    def _make(
        issue_date_: date | None = None,
        title: str = "Test Issue",
        status: str = "review_required",
        expert_entries: list[tuple[int, bool]] | None = None,
        practical_entries: list[tuple[int, bool]] | None = None,
        expert_section_md: str | None = None,
        practical_section_md: str | None = None,
    ) -> NewsletterIssue:
        blob: dict[str, list[dict[str, object]]] = {}
        if expert_entries is not None:
            blob["expert"] = [{"id": pid, "included": inc} for pid, inc in expert_entries]
        if practical_entries is not None:
            blob["practical"] = [{"id": pid, "included": inc} for pid, inc in practical_entries]
        issue = NewsletterIssue(
            issue_date=issue_date_ or date(2026, 5, 18),
            title=title,
            status=status,
            candidate_ids_json=json.dumps(blob) if blob else None,
            expert_section_md=expert_section_md,
            practical_section_md=practical_section_md,
        )
        db_session.add(issue)
        db_session.flush()
        return issue

    return _make
