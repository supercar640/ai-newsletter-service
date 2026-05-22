"""Data access for Competitor rows.

Aliases are stored as JSON text on the row; the repository handles the
(de)serialization so the rest of the slice deals with plain ``list[str]``.
Mirrors the interests-registry pattern.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from newsletter.models.competitor import Competitor
from newsletter.slices.competitors.schemas import CompetitorCreate, CompetitorUpdate


class CompetitorAlreadyExistsError(Exception):
    """Raised when ``add`` is called with an already-used name."""


class CompetitorNotFoundError(Exception):
    """Raised when an operation references a missing competitor id."""


def list_competitors(session: Session, *, only_enabled: bool = False) -> list[Competitor]:
    stmt = select(Competitor).order_by(Competitor.id)
    if only_enabled:
        stmt = stmt.where(Competitor.enabled.is_(True))
    return list(session.scalars(stmt).all())


def get(session: Session, competitor_id: int) -> Competitor | None:
    return session.get(Competitor, competitor_id)


def get_or_raise(session: Session, competitor_id: int) -> Competitor:
    row = get(session, competitor_id)
    if row is None:
        raise CompetitorNotFoundError(competitor_id)
    return row


def add(session: Session, payload: CompetitorCreate) -> Competitor:
    row = Competitor(
        name=payload.name,
        aliases_json=_dump_aliases(payload.aliases),
        enabled=payload.enabled,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise CompetitorAlreadyExistsError(payload.name) from exc
    return row


def update(session: Session, competitor_id: int, payload: CompetitorUpdate) -> Competitor:
    row = get_or_raise(session, competitor_id)
    changes = payload.model_dump(exclude_unset=True)
    if "aliases" in changes and changes["aliases"] is not None:
        row.aliases_json = _dump_aliases(changes["aliases"])
        del changes["aliases"]
    for key, value in changes.items():
        setattr(row, key, value)
    session.flush()
    return row


def disable(session: Session, competitor_id: int) -> Competitor:
    row = get_or_raise(session, competitor_id)
    row.enabled = False
    session.flush()
    return row


def remove(session: Session, competitor_id: int) -> None:
    row = get_or_raise(session, competitor_id)
    session.delete(row)
    session.flush()


def load_aliases(row: Competitor) -> list[str]:
    """Parse the JSON aliases column. Tolerant of malformed payloads."""
    try:
        parsed = json.loads(row.aliases_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(a) for a in parsed if a]


def _dump_aliases(aliases: Sequence[str]) -> str:
    cleaned = [a.strip() for a in aliases if a and a.strip()]
    return json.dumps(cleaned, ensure_ascii=False)
