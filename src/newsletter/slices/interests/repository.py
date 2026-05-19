"""Data access for CompanyInterest rows.

Pure functions over a SQLAlchemy session. Keywords are stored as JSON
text on the row; the repository handles the (de)serialization so the
rest of the slice deals with plain ``list[str]``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from newsletter.models.company_interest import CompanyInterest
from newsletter.slices.interests.schemas import InterestCreate, InterestUpdate


class InterestAlreadyExistsError(Exception):
    """Raised when ``add`` is called with an already-used name."""


class InterestNotFoundError(Exception):
    """Raised when an operation references a missing interest id."""


def list_interests(session: Session, *, only_enabled: bool = False) -> list[CompanyInterest]:
    stmt = select(CompanyInterest).order_by(CompanyInterest.id)
    if only_enabled:
        stmt = stmt.where(CompanyInterest.enabled.is_(True))
    return list(session.scalars(stmt).all())


def get(session: Session, interest_id: int) -> CompanyInterest | None:
    return session.get(CompanyInterest, interest_id)


def get_or_raise(session: Session, interest_id: int) -> CompanyInterest:
    row = get(session, interest_id)
    if row is None:
        raise InterestNotFoundError(interest_id)
    return row


def add(session: Session, payload: InterestCreate) -> CompanyInterest:
    row = CompanyInterest(
        name=payload.name,
        description=payload.description,
        keywords_json=_dump_keywords(payload.keywords),
        weight=payload.weight,
        enabled=payload.enabled,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise InterestAlreadyExistsError(payload.name) from exc
    return row


def update(session: Session, interest_id: int, payload: InterestUpdate) -> CompanyInterest:
    row = get_or_raise(session, interest_id)
    changes = payload.model_dump(exclude_unset=True)
    if "keywords" in changes and changes["keywords"] is not None:
        row.keywords_json = _dump_keywords(changes["keywords"])
        del changes["keywords"]
    for key, value in changes.items():
        setattr(row, key, value)
    session.flush()
    return row


def disable(session: Session, interest_id: int) -> CompanyInterest:
    row = get_or_raise(session, interest_id)
    row.enabled = False
    session.flush()
    return row


def remove(session: Session, interest_id: int) -> None:
    row = get_or_raise(session, interest_id)
    session.delete(row)
    session.flush()


def set_embedding(
    session: Session,
    interest_id: int,
    *,
    vector_bytes: bytes,
    model: str,
) -> CompanyInterest:
    """Attach an embedding to an existing interest row."""
    row = get_or_raise(session, interest_id)
    row.embedding = vector_bytes
    row.embedding_model = model
    session.flush()
    return row


def load_keywords(row: CompanyInterest) -> list[str]:
    """Parse the JSON keywords column. Tolerant of malformed payloads."""
    try:
        parsed = json.loads(row.keywords_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(k) for k in parsed if k]


def _dump_keywords(keywords: Sequence[str]) -> str:
    cleaned = [k.strip() for k in keywords if k and k.strip()]
    return json.dumps(cleaned, ensure_ascii=False)
