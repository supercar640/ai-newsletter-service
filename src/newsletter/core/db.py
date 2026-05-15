"""SQLAlchemy engine / session / Base for the whole app.

Slices import ``Base`` to declare models and ``session_scope`` to read/write.
The engine is created lazily on first use so test fixtures can override
the DB URL before construction.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from newsletter.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base shared across all models."""


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args: dict[str, object] = {}
        if settings.db_url.startswith("sqlite"):
            # Allow cross-thread use; FK enforcement enabled via PRAGMA below.
            connect_args["check_same_thread"] = False
        _engine = create_engine(settings.db_url, future=True, connect_args=connect_args)
        if settings.db_url.startswith("sqlite"):
            _enable_sqlite_foreign_keys(_engine)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context-managed session with commit/rollback semantics."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine_for_tests() -> None:
    """Drop cached engine/sessionmaker so tests can swap DB URL."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
