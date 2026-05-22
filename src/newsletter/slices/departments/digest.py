"""Department digest: per-department most-relevant items over a window.

Embedding mode (cosine) when the embedding client yields department vectors,
else keyword-overlap fallback. Read-only; no sending. Window/anchor philosophy
mirrors trends/competitors (published_at, else created_at, naive UTC).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from newsletter.core.embeddings import EmbeddingClient, deserialize
from newsletter.models.processed_item import ProcessedItem
from newsletter.models.raw_item import RawItem
from newsletter.slices.departments import repository
from newsletter.slices.departments.relevance import (
    department_tokens,
    embedding_score,
    keyword_score,
)
from newsletter.slices.departments.schemas import (
    DepartmentDigest,
    DepartmentDigestEntry,
    RelevantHeadline,
)


def build_department_digest(
    session: Session,
    *,
    days: int = 7,
    until: date | None = None,
    since: date | None = None,
    top_k: int = 5,
    embed_client: EmbeddingClient,
) -> DepartmentDigest:
    """Per-department top-relevant items for one look-back window."""
    until_date = until or (date.today() + timedelta(days=1))
    since_date = since or (until_date - timedelta(days=days))
    lo = datetime.combine(since_date, time.min)
    hi = datetime.combine(until_date, time.min)

    depts = repository.list_departments(session, only_enabled=True)
    dept_texts = [f"{d.name} {d.description or ''}" for d in depts]
    dept_vectors = embed_client.embed(dept_texts) if depts else []
    embedding_mode = bool(depts) and len(dept_vectors) == len(depts) and any(dept_vectors)
    mode = "embedding" if embedding_mode else "keyword"

    dept_tok = [department_tokens(d.name, d.description) for d in depts]

    items: list[tuple[str, str, str, list[float]]] = []
    total_items = 0
    for title, url, summary, emb, published_at, created_at in _fetch(session, lo, hi):
        anchor = _anchor(published_at, created_at)
        if anchor is None or not (lo <= anchor < hi):
            continue
        total_items += 1
        items.append((title, url, f"{title or ''} {summary or ''}", deserialize(emb)))

    entries: list[DepartmentDigestEntry] = []
    for idx, _dept in enumerate(depts):
        scored: list[RelevantHeadline] = []
        for title, url, text, vec in items:
            if embedding_mode:
                score = embedding_score(dept_vectors[idx], vec)
            else:
                score = float(keyword_score(dept_tok[idx], text))
            if score > 0:
                scored.append(RelevantHeadline(title=title, url=url, score=score))
        scored.sort(key=lambda h: h.score, reverse=True)
        entries.append(DepartmentDigestEntry(name=_dept.name, headlines=scored[:top_k]))

    return DepartmentDigest(
        since=since_date,
        until=until_date,
        total_items=total_items,
        mode=mode,
        departments=entries,
    )


def _fetch(session: Session, lo: datetime, hi: datetime):
    """Rows whose anchor (published_at, else created_at) falls in [lo, hi)."""
    stmt = (
        select(
            ProcessedItem.normalized_title,
            ProcessedItem.canonical_url,
            ProcessedItem.summary,
            ProcessedItem.embedding,
            RawItem.published_at,
            ProcessedItem.created_at,
        )
        .join(RawItem, RawItem.id == ProcessedItem.raw_item_id)
        .where(
            or_(
                and_(
                    RawItem.published_at.is_not(None),
                    RawItem.published_at >= lo,
                    RawItem.published_at < hi,
                ),
                and_(
                    RawItem.published_at.is_(None),
                    ProcessedItem.created_at >= lo,
                    ProcessedItem.created_at < hi,
                ),
            )
        )
    )
    return session.execute(stmt).all()


def _anchor(published_at: datetime | None, created_at: datetime | None) -> datetime | None:
    dt = published_at if published_at is not None else created_at
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


__all__ = ["build_department_digest"]
