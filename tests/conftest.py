"""Shared pytest fixtures.

Every test runs against an in-memory SQLite so suites are isolated and fast.
The global engine/sessionmaker cache is reset per-test to avoid cross-test
state bleed.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from newsletter.core import db as core_db
from newsletter.core.config import Settings, get_settings
from newsletter.core.logging import configure_logging


@pytest.fixture(autouse=True)
def _configure_logging() -> None:
    configure_logging(log_format="console", log_level="WARNING")


# Only credential / identifier env vars (all string-typed). Non-string typed
# settings (SMTP_PORT, YOUTUBE_FETCH_METADATA) must not be set to "" or
# pydantic-settings will reject them.
_EXTERNAL_CREDENTIAL_VARS = (
    "ANTHROPIC_API_KEY",
    "NAVER_CLIENT_ID",
    "NAVER_CLIENT_SECRET",
    "YOUTUBE_API_KEY",
    "SMTP_HOST",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "NEWSLETTER_RECIPIENTS",
)


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """In-memory SQLite + test env. Clears all external-API vars so
    real credentials never leak into tests; individual tests opt back
    in via their own monkeypatch.
    """
    monkeypatch.setenv("DB_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ENV", "test")
    # setenv("") (not delenv) so an on-disk .env can't repopulate these.
    for name in _EXTERNAL_CREDENTIAL_VARS:
        monkeypatch.setenv(name, "")
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def db_session(settings: Settings) -> Iterator[Session]:
    """Fresh in-memory DB with schema created. Yields a session."""
    core_db.reset_engine_for_tests()
    # Import models so Base.metadata sees them. (No-op while models is empty;
    # required once slices start adding tables.)
    import newsletter.models  # noqa: F401

    engine = core_db.get_engine()
    core_db.Base.metadata.create_all(engine)

    session_factory = core_db.get_sessionmaker()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        core_db.Base.metadata.drop_all(engine)
        core_db.reset_engine_for_tests()
