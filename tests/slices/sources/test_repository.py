"""Source Registry repository tests."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from newsletter.slices.sources import repository
from newsletter.slices.sources.schemas import SourceCreate, SourceUpdate


def _payload(source_id: str = "naver-ai", **overrides: object) -> SourceCreate:
    base: dict[str, object] = {
        "source_id": source_id,
        "name": "Naver News — AI",
        "type": "NAVER_API",
        "content_track": "expert_news",
        "endpoint": "https://example.com",
    }
    base.update(overrides)
    return SourceCreate(**base)


def test_add_persists_source(db_session: Session) -> None:
    source = repository.add(db_session, _payload())
    db_session.commit()

    fetched = repository.get(db_session, "naver-ai")
    assert fetched is not None
    assert fetched.source_id == source.source_id
    assert fetched.priority == "medium"
    assert fetched.enabled is True
    assert fetched.created_at is not None


def test_add_duplicate_raises(db_session: Session) -> None:
    repository.add(db_session, _payload())
    db_session.commit()

    with pytest.raises(repository.SourceAlreadyExistsError):
        repository.add(db_session, _payload())


def test_get_missing_returns_none(db_session: Session) -> None:
    assert repository.get(db_session, "nope") is None


def test_get_or_raise_missing(db_session: Session) -> None:
    with pytest.raises(repository.SourceNotFoundError):
        repository.get_or_raise(db_session, "nope")


def test_list_sources_sorted(db_session: Session) -> None:
    repository.add(db_session, _payload("zeta"))
    repository.add(db_session, _payload("alpha"))
    repository.add(db_session, _payload("mike"))
    db_session.commit()

    ids = [s.source_id for s in repository.list_sources(db_session)]
    assert ids == ["alpha", "mike", "zeta"]


def test_list_only_enabled(db_session: Session) -> None:
    repository.add(db_session, _payload("a"))
    repository.add(db_session, _payload("b"))
    repository.disable(db_session, "b")
    db_session.commit()

    enabled_ids = [s.source_id for s in repository.list_sources(db_session, only_enabled=True)]
    assert enabled_ids == ["a"]


def test_update_changes_fields(db_session: Session) -> None:
    repository.add(db_session, _payload())
    db_session.commit()

    updated = repository.update(
        db_session, "naver-ai", SourceUpdate(priority="high", name="Renamed")
    )
    db_session.commit()

    assert updated.priority == "high"
    assert updated.name == "Renamed"


def test_disable_then_enable(db_session: Session) -> None:
    repository.add(db_session, _payload())
    db_session.commit()

    repository.disable(db_session, "naver-ai")
    db_session.commit()
    assert repository.get_or_raise(db_session, "naver-ai").enabled is False

    repository.enable(db_session, "naver-ai")
    db_session.commit()
    assert repository.get_or_raise(db_session, "naver-ai").enabled is True


def test_disable_missing_raises(db_session: Session) -> None:
    with pytest.raises(repository.SourceNotFoundError):
        repository.disable(db_session, "ghost")


def test_upsert_creates_then_updates(db_session: Session) -> None:
    payload = _payload()
    source, created = repository.upsert(db_session, payload)
    db_session.commit()
    assert created is True
    assert source.priority == "medium"

    again, created = repository.upsert(
        db_session,
        _payload(priority="high", name="Bumped"),
    )
    db_session.commit()
    assert created is False
    assert again.priority == "high"
    assert again.name == "Bumped"


def test_check_constraint_rejects_bad_enum(db_session: Session) -> None:
    """If raw SQL inserts an invalid enum, the CHECK constraint fires.

    Pydantic guards normal callers; this verifies the DB-side safety net.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO sources (source_id, name, type, content_track, endpoint, "
                "priority, trust_level, enabled, fetch_interval, auth_required) "
                "VALUES ('x', 'x', 'NOT_A_TYPE', 'expert_news', 'http://x', "
                "'medium', 'media', 1, 'daily', 0)"
            )
        )
        db_session.flush()
