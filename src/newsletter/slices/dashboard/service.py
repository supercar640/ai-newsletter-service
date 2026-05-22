"""Performance dashboard aggregation over collected/processed items.

Read-only. Computes per-source yield (collected vs processed) and quality
(average scores, track split, top categories, dedup effectiveness) for one
look-back window on the indexed ``RawItem.collected_at``. Complements
``newsletter stats``, which covers operational/cost metrics from RunLog.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.models.source import Source
from newsletter.slices.dashboard.schemas import (
    DashboardReport,
    QualitySummary,
    SourceStat,
)


def build_dashboard(
    session: Session,
    *,
    days: int = 30,
    until: date | None = None,
    since: date | None = None,
    top_categories: int = 10,
) -> DashboardReport:
    """Aggregate per-source yield + quality for one look-back window."""
    until_date = until or (date.today() + timedelta(days=1))
    since_date = since or (until_date - timedelta(days=days))
    lo = datetime.combine(since_date, time.min)
    hi = datetime.combine(until_date, time.min)

    meta = {
        sid: (name, track)
        for sid, name, track in session.execute(
            select(Source.source_id, Source.name, Source.content_track)
        ).all()
    }

    rows = session.execute(
        select(
            RawItem.source_id,
            ProcessedItem.id,
            ProcessedItem.relevance_score,
            ProcessedItem.importance_score,
            ProcessedItem.content_track,
            ProcessedItem.category,
            ProcessedItem.duplicate_group_id,
        )
        .select_from(RawItem)
        .join(ProcessedItem, ProcessedItem.raw_item_id == RawItem.id, isouter=True)
        .where(RawItem.collected_at >= lo, RawItem.collected_at < hi)
    ).all()

    collected: dict[str, int] = {}
    processed: dict[str, int] = {}
    rel_sum: dict[str, float] = {}
    imp_sum: dict[str, float] = {}

    total_collected = 0
    total_processed = 0
    track_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    groups: set[str] = set()
    grouped_items = 0

    for sid, pid, rel, imp, track, category, dgid in rows:
        total_collected += 1
        collected[sid] = collected.get(sid, 0) + 1
        if pid is not None:
            total_processed += 1
            processed[sid] = processed.get(sid, 0) + 1
            rel_sum[sid] = rel_sum.get(sid, 0.0) + (rel or 0.0)
            imp_sum[sid] = imp_sum.get(sid, 0.0) + (imp or 0.0)
            if track:
                track_counts[track] = track_counts.get(track, 0) + 1
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1
            if dgid:
                groups.add(dgid)
                grouped_items += 1

    sources: list[SourceStat] = []
    for sid, count in collected.items():
        proc = processed.get(sid, 0)
        name, track = meta.get(sid, (sid, "?"))
        sources.append(
            SourceStat(
                source_id=sid,
                name=name,
                content_track=track,
                collected=count,
                processed=proc,
                avg_relevance=round(rel_sum.get(sid, 0.0) / proc, 10) if proc else 0.0,
                avg_importance=round(imp_sum.get(sid, 0.0) / proc, 10) if proc else 0.0,
            )
        )
    sources.sort(key=lambda s: (-s.collected, s.name))

    top_cats = sorted(category_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top_categories]

    return DashboardReport(
        since=since_date,
        until=until_date,
        sources=sources,
        quality=QualitySummary(
            total_collected=total_collected,
            total_processed=total_processed,
            track_counts=track_counts,
            top_categories=top_cats,
            distinct_groups=len(groups),
            grouped_items=grouped_items,
        ),
    )


__all__ = ["build_dashboard"]
