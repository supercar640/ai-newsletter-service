"""Orchestrate processing for unprocessed ``RawItem`` rows."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.core.llm import LLMClient
from newsletter.core.logging import get_logger
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.models.source import Source
from newsletter.slices.processing.dedupe import DedupeInput, assign_groups
from newsletter.slices.processing.normalize import canonical_url, normalize_title
from newsletter.slices.processing.relevance import RelevanceVerdict, assess
from newsletter.slices.processing.track_classifier import classify

log = get_logger(__name__)


@dataclass
class ProcessingReport:
    fetched: int = 0
    processed: int = 0
    filtered_out: int = 0
    errors: list[tuple[int, str]] = field(default_factory=list)
    per_track: dict[str, int] = field(default_factory=dict)


def process(
    session: Session,
    *,
    llm: LLMClient | None = None,
    keyword_only: bool = False,
    raw_item_ids: list[int] | None = None,
    min_relevance: float = 0.0,
) -> ProcessingReport:
    """Process every RawItem that does not yet have a ProcessedItem.

    Parameters
    ----------
    llm:
        LLM client for ambiguous-relevance + 'both'-track items. If
        ``None``, behaves the same as ``keyword_only=True``.
    keyword_only:
        Skip LLM calls entirely (cheaper, lower accuracy).
    raw_item_ids:
        Restrict processing to a specific subset (for retry / debug).
    min_relevance:
        Drop items whose final relevance score is below this threshold.
        ``0.0`` keeps everything that has any AI signal.
    """
    raws = _fetch_pending(session, raw_item_ids)
    report = ProcessingReport(fetched=len(raws))
    if not raws:
        return report

    sources_by_id = _load_sources(session, {r.source_id for r in raws})

    # Build canonical urls + titles up front so dedupe groups them together.
    pre = [
        (
            raw,
            normalize_title(raw.title),
            canonical_url(raw.url) or raw.url,
        )
        for raw in raws
    ]

    groups = assign_groups(
        DedupeInput(
            key=raw.id,
            canonical_url=url,
            title=title,
            published_at=raw.published_at,
        )
        for raw, title, url in pre
    )

    for raw, normalized, canon in pre:
        source = sources_by_id.get(raw.source_id)
        if source is None:
            report.errors.append((raw.id, f"missing source row {raw.source_id!r}"))
            continue

        verdict = assess(
            normalized,
            raw.raw_summary,
            llm=None if keyword_only else llm,
            keyword_only=keyword_only,
        )
        if verdict.score < min_relevance and not verdict.is_ai:
            report.filtered_out += 1
            continue

        track = classify(source, normalized, raw.raw_summary, llm=llm)

        keywords_str = ",".join(verdict.matched_keywords) or None
        item = ProcessedItem(
            raw_item_id=raw.id,
            normalized_title=normalized,
            canonical_url=canon,
            content_track=track,
            category=source.category,
            relevance_score=verdict.score,
            importance_score=0.0,  # filled by integration slice later
            summary=raw.raw_summary,
            keywords=keywords_str,
            duplicate_group_id=groups.get(raw.id),
        )
        session.add(item)
        report.processed += 1
        report.per_track[track] = report.per_track.get(track, 0) + 1

    session.flush()
    log.info(
        "processing.done",
        fetched=report.fetched,
        processed=report.processed,
        filtered_out=report.filtered_out,
        per_track=report.per_track,
    )
    return report


def _fetch_pending(session: Session, raw_item_ids: list[int] | None) -> list[RawItem]:
    """Return raw items that don't yet have a ProcessedItem row."""
    sub = select(ProcessedItem.raw_item_id)
    stmt = select(RawItem).where(RawItem.id.not_in(sub)).order_by(RawItem.id)
    if raw_item_ids is not None:
        stmt = stmt.where(RawItem.id.in_(raw_item_ids))
    return list(session.scalars(stmt).all())


def _load_sources(session: Session, source_ids: set[str]) -> dict[str, Source]:
    if not source_ids:
        return {}
    rows = session.scalars(select(Source).where(Source.source_id.in_(source_ids))).all()
    return {row.source_id: row for row in rows}


# Re-exports for slice consumers
__all__ = ["ProcessingReport", "RelevanceVerdict", "process"]
