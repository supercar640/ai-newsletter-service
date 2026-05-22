"""competitors.repository — registry CRUD + alias (de)serialization."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from newsletter.slices.competitors import repository
from newsletter.slices.competitors.schemas import CompetitorCreate, CompetitorUpdate


def test_add_and_load_aliases(db_session: Session):
    row = repository.add(
        db_session,
        CompetitorCreate(name="OpenAI", aliases=["OpenAI", " GPT ", ""]),
    )
    db_session.commit()
    assert row.id is not None
    # blanks stripped, empties dropped
    assert repository.load_aliases(row) == ["OpenAI", "GPT"]


def test_add_duplicate_name_raises(db_session: Session):
    repository.add(db_session, CompetitorCreate(name="OpenAI"))
    db_session.commit()
    with pytest.raises(repository.CompetitorAlreadyExistsError):
        repository.add(db_session, CompetitorCreate(name="OpenAI"))


def test_list_only_enabled_filters(db_session: Session):
    repository.add(db_session, CompetitorCreate(name="OpenAI", enabled=True))
    repository.add(db_session, CompetitorCreate(name="Cohere", enabled=False))
    db_session.commit()
    all_rows = repository.list_competitors(db_session)
    enabled = repository.list_competitors(db_session, only_enabled=True)
    assert len(all_rows) == 2
    assert [r.name for r in enabled] == ["OpenAI"]


def test_update_replaces_aliases(db_session: Session):
    row = repository.add(db_session, CompetitorCreate(name="Google", aliases=["bard"]))
    db_session.commit()
    repository.update(db_session, row.id, CompetitorUpdate(aliases=["gemini", "deepmind"]))
    db_session.commit()
    db_session.expire_all()
    assert repository.load_aliases(repository.get(db_session, row.id)) == [
        "gemini",
        "deepmind",
    ]


def test_disable_and_remove(db_session: Session):
    row = repository.add(db_session, CompetitorCreate(name="Meta"))
    db_session.commit()
    repository.disable(db_session, row.id)
    db_session.commit()
    db_session.expire_all()
    assert repository.get(db_session, row.id).enabled is False
    repository.remove(db_session, row.id)
    db_session.commit()
    assert repository.get(db_session, row.id) is None


def test_load_aliases_tolerates_malformed_json(db_session: Session):
    row = repository.add(db_session, CompetitorCreate(name="X"))
    row.aliases_json = "{not json"
    db_session.flush()
    assert repository.load_aliases(row) == []


def test_get_or_raise_missing(db_session: Session):
    with pytest.raises(repository.CompetitorNotFoundError):
        repository.get_or_raise(db_session, 999)
