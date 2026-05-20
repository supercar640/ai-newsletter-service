"""Data access for Department rows. Pure functions over a session.

Mirrors :mod:`newsletter.slices.interests.repository` minus the embedding
machinery — departments carry only name/description/enabled.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from newsletter.models.department import Department
from newsletter.slices.departments.schemas import DepartmentCreate, DepartmentUpdate


class DepartmentAlreadyExistsError(Exception):
    """Raised when ``add`` is called with an already-used name."""


class DepartmentNotFoundError(Exception):
    """Raised when an operation references a missing department id."""


def list_departments(session: Session, *, only_enabled: bool = False) -> list[Department]:
    stmt = select(Department).order_by(Department.id)
    if only_enabled:
        stmt = stmt.where(Department.enabled.is_(True))
    return list(session.scalars(stmt).all())


def get(session: Session, department_id: int) -> Department | None:
    return session.get(Department, department_id)


def get_or_raise(session: Session, department_id: int) -> Department:
    row = get(session, department_id)
    if row is None:
        raise DepartmentNotFoundError(department_id)
    return row


def add(session: Session, payload: DepartmentCreate) -> Department:
    row = Department(
        name=payload.name,
        description=payload.description,
        enabled=payload.enabled,
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise DepartmentAlreadyExistsError(payload.name) from exc
    return row


def update(session: Session, department_id: int, payload: DepartmentUpdate) -> Department:
    row = get_or_raise(session, department_id)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(row, key, value)
    session.flush()
    return row


def disable(session: Session, department_id: int) -> Department:
    row = get_or_raise(session, department_id)
    row.enabled = False
    session.flush()
    return row


def remove(session: Session, department_id: int) -> None:
    row = get_or_raise(session, department_id)
    session.delete(row)
    session.flush()
