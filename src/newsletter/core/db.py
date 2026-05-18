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
from sqlalchemy.pool import StaticPool

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
        engine_kwargs: dict[str, object] = {"future": True}
        if settings.db_url.startswith("sqlite"):
            # Allow cross-thread use; FK enforcement enabled via PRAGMA below.
            connect_args["check_same_thread"] = False
            # ":memory:" gives a fresh DB per connection by default. StaticPool
            # pins one connection so the schema/test data is visible to every
            # session (including the threadpool starlette uses for sync deps).
            if ":memory:" in settings.db_url:
                engine_kwargs["poolclass"] = StaticPool
        engine_kwargs["connect_args"] = connect_args
        _engine = create_engine(settings.db_url, **engine_kwargs)
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
