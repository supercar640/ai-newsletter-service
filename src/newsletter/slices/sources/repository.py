"""Data access for the Source Registry.

Pure functions over a SQLAlchemy ``Session`` — the slice's only path to
persistence. No I/O outside the DB lives here.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from newsletter.models.source import Source
from newsletter.slices.sources.schemas import SourceCreate, SourceUpdate


class SourceAlreadyExistsError(Exception):
    """Raised when ``add`` is called with an already-used ``source_id``."""


class SourceNotFoundError(Exception):
    """Raised when an operation references a missing ``source_id``."""


def list_sources(session: Session, *, only_enabled: bool = False) -> list[Source]:
    stmt = select(Source).order_by(Source.source_id)
    if only_enabled:
        stmt = stmt.where(Source.enabled.is_(True))
    return list(session.scalars(stmt).all())


def get(session: Session, source_id: str) -> Source | None:
    return session.get(Source, source_id)


def get_or_raise(session: Session, source_id: str) -> Source:
    source = get(session, source_id)
    if source is None:
        raise SourceNotFoundError(source_id)
    return source


def add(session: Session, payload: SourceCreate) -> Source:
    source = Source(**payload.model_dump())
    session.add(source)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise SourceAlreadyExistsError(payload.source_id) from exc
    return source


def update(session: Session, source_id: str, payload: SourceUpdate) -> Source:
    source = get_or_raise(session, source_id)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(source, key, value)
    session.flush()
    return source


def disable(session: Session, source_id: str) -> Source:
    source = get_or_raise(session, source_id)
    source.enabled = False
    session.flush()
    return source


def enable(session: Session, source_id: str) -> Source:
    source = get_or_raise(session, source_id)
    source.enabled = True
    session.flush()
    return source


def upsert(session: Session, payload: SourceCreate) -> tuple[Source, bool]:
    """Insert if absent, update otherwise. Returns ``(source, created)``."""
    existing = get(session, payload.source_id)
    if existing is None:
        return add(session, payload), True
    update_payload = SourceUpdate.model_validate(payload.model_dump(exclude={"source_id"}))
    return update(session, payload.source_id, update_payload), False
