"""Shared FastAPI dependencies for the admin slice."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from newsletter.core.db import get_sessionmaker


def get_db() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
