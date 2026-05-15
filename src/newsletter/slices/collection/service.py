"""Orchestrate collection across all enabled sources.

The service walks the Source Registry, asks each collector for items,
and persists them as :class:`RawItem`. Duplicate items (same
``(source_id, url)``) are skipped without raising.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.core.logging import get_logger
from newsletter.models.raw_item import RawItem
from newsletter.models.source import Source
from newsletter.slices.collection.base import (
    CollectorError,
    CollectorResult,
    UnsupportedSourceTypeError,
)
from newsletter.slices.collection.registry import get_collector
from newsletter.slices.sources import repository as sources_repo

log = get_logger(__name__)


@dataclass
class SourceReport:
    """Per-source outcome of a collection run."""

    source_id: str
    fetched: int = 0
    inserted: int = 0
    skipped_duplicate: int = 0
    error: str | None = None


@dataclass
class CollectionReport:
    """Aggregate outcome of one :func:`collect_all` run."""

    per_source: list[SourceReport] = field(default_factory=list)
    skipped_unsupported: int = 0

    @property
    def total_inserted(self) -> int:
        return sum(s.inserted for s in self.per_source)

    @property
    def total_fetched(self) -> int:
        return sum(s.fetched for s in self.per_source)

    @property
    def total_duplicates(self) -> int:
        return sum(s.skipped_duplicate for s in self.per_source)

    @property
    def errors(self) -> list[SourceReport]:
        return [s for s in self.per_source if s.error]


def collect_all(
    session: Session,
    *,
    source_ids: list[str] | None = None,
    collector_factory=None,
) -> CollectionReport:
    """Collect from every enabled source (or the subset given).

    Parameters
    ----------
    session:
        Active SQLAlchemy session. Caller commits.
    source_ids:
        If provided, restrict to these sources (still must be enabled).
    collector_factory:
        Override the per-type collector resolver (used in tests). Receives
        the source type string and must return a :class:`Collector`.
    """
    factory = collector_factory or get_collector
    sources = sources_repo.list_sources(session, only_enabled=True)
    if source_ids:
        wanted = set(source_ids)
        sources = [s for s in sources if s.source_id in wanted]

    report = CollectionReport()
    for source in sources:
        report.per_source.append(_collect_one(session, source, factory))
    return report


def _collect_one(
    session: Session,
    source: Source,
    factory,
) -> SourceReport:
    src_report = SourceReport(source_id=source.source_id)
    try:
        collector = factory(source.type)
    except UnsupportedSourceTypeError:
        src_report.error = f"unsupported source type: {source.type}"
        log.warning("collect.unsupported", source=source.source_id, type=source.type)
        return src_report

    try:
        items = collector.collect(source)
    except CollectorError as exc:
        src_report.error = str(exc)
        log.warning("collect.error", source=source.source_id, error=str(exc))
        return src_report
    except Exception as exc:
        src_report.error = f"{type(exc).__name__}: {exc}"
        log.exception("collect.unexpected", source=source.source_id)
        return src_report
    finally:
        close = getattr(collector, "close", None)
        if callable(close):
            close()

    src_report.fetched = len(items)
    if not items:
        return src_report

    existing = set(
        session.scalars(select(RawItem.url).where(RawItem.source_id == source.source_id)).all()
    )
    seen_in_batch: set[str] = set()
    for item in items:
        if item.url in existing or item.url in seen_in_batch:
            src_report.skipped_duplicate += 1
            continue
        seen_in_batch.add(item.url)
        session.add(_to_raw(source, item))
        src_report.inserted += 1

    session.flush()
    log.info(
        "collect.source",
        source=source.source_id,
        fetched=src_report.fetched,
        inserted=src_report.inserted,
        duplicates=src_report.skipped_duplicate,
    )
    return src_report


def _to_raw(source: Source, item: CollectorResult) -> RawItem:
    return RawItem(
        source_id=source.source_id,
        title=item.title,
        url=item.url,
        published_at=item.published_at,
        author=item.author,
        raw_summary=item.raw_summary,
        raw_content=item.raw_content,
        language=item.language or source.language,
    )
