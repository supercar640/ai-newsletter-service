"""Orchestrate scoring → clustering → candidate selection over the DB.

The service is the only place that touches SQLAlchemy. Pure-function
modules (``scoring``, ``clustering``, ``candidates``) work on dataclasses
the service materializes by joining ProcessedItem → RawItem → Source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.core.embeddings import deserialize
from newsletter.core.llm import LLMClient
from newsletter.core.logging import get_logger
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.models.source import Source
from newsletter.slices.integration.candidates import (
    Candidate,
    CandidateInput,
    select_candidates,
)
from newsletter.slices.integration.clustering import ClusterInput, cluster_items
from newsletter.slices.integration.scoring import ScoreInput, score_items

log = get_logger(__name__)


@dataclass(slots=True)
class IntegrationReport:
    scored: int = 0
    clusters: int = 0
    expert_candidates: list[Candidate] = field(default_factory=list)
    practical_candidates: list[Candidate] = field(default_factory=list)


def integrate(
    session: Session,
    *,
    llm: LLMClient | None = None,
    now: datetime | None = None,
    expert_count: int = 7,
    practical_count: int = 4,
    top_k_for_llm: int = 20,
    half_life_days: float = 3.0,
    max_per_category: int = 2,
    cosine_threshold: float = 0.85,
) -> IntegrationReport:
    """Run integration over every ProcessedItem row.

    Side effect: writes the final ``importance_score`` back to each
    ProcessedItem row (idempotent, recency-dependent).
    """
    now = now or datetime.now(UTC)

    rows = _fetch_processed_with_context(session)
    if not rows:
        return IntegrationReport()

    score_inputs: list[ScoreInput] = []
    cluster_inputs: list[ClusterInput] = []
    track_by_id: dict[int, str] = {}
    category_by_id: dict[int, str | None] = {}
    embeddings: dict[int, list[float]] = {}

    for proc, raw, source in rows:
        published = _to_aware(raw.published_at) if raw else None
        score_inputs.append(
            ScoreInput(
                id=proc.id,
                trust_level=source.trust_level if source else "media",
                published_at=published,
                title=proc.normalized_title,
                summary=proc.summary,
                source_name=source.name if source else "(unknown)",
            )
        )
        cluster_inputs.append(
            ClusterInput(
                id=proc.id,
                title=proc.normalized_title,
                duplicate_group_id=proc.duplicate_group_id,
            )
        )
        track_by_id[proc.id] = proc.content_track
        category_by_id[proc.id] = proc.category
        if proc.embedding:
            embeddings[proc.id] = deserialize(proc.embedding)

    scores = score_items(
        score_inputs,
        llm=llm,
        now=now,
        top_k_for_llm=top_k_for_llm,
        half_life_days=half_life_days,
    )

    # Persist importance_score.
    for proc, _raw, _source in rows:
        proc.importance_score = float(scores.get(proc.id, 0.0))
    session.flush()

    clusters = cluster_items(
        cluster_inputs,
        embeddings=embeddings or None,
        cosine_threshold=cosine_threshold,
    )

    cand_inputs = [
        CandidateInput(
            id=item_id,
            track=track_by_id[item_id],
            category=category_by_id[item_id],
            cluster_id=clusters[item_id],
            score=scores[item_id],
        )
        for item_id in scores
    ]
    selected = select_candidates(
        cand_inputs,
        expert_count=expert_count,
        practical_count=practical_count,
        max_per_category=max_per_category,
    )

    report = IntegrationReport(
        scored=len(scores),
        clusters=len(set(clusters.values())),
        expert_candidates=selected["expert_news"],
        practical_candidates=selected["practical_insight"],
    )
    log.info(
        "integration.done",
        scored=report.scored,
        clusters=report.clusters,
        expert_candidates=len(report.expert_candidates),
        practical_candidates=len(report.practical_candidates),
        items_with_embedding=len(embeddings),
    )
    return report


def _fetch_processed_with_context(
    session: Session,
) -> list[tuple[ProcessedItem, RawItem | None, Source | None]]:
    """Join ProcessedItem with its RawItem and Source so scoring has trust + time."""
    stmt = (
        select(ProcessedItem, RawItem, Source)
        .join(RawItem, RawItem.id == ProcessedItem.raw_item_id)
        .join(Source, Source.source_id == RawItem.source_id, isouter=True)
        .order_by(ProcessedItem.id)
    )
    return list(session.execute(stmt).all())  # type: ignore[return-value]


def _to_aware(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; treat naïve datetimes as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


__all__ = ["IntegrationReport", "integrate"]
