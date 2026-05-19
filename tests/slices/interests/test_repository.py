"""interests.repository — CRUD + keyword (de)serialization."""

from __future__ import annotations

import pytest

from newsletter.slices.interests import repository
from newsletter.slices.interests.schemas import InterestCreate, InterestUpdate


def test_add_and_get(db_session):
    payload = InterestCreate(
        name="RAG",
        description="Retrieval-Augmented Generation",
        keywords=["rag", "검색 증강"],
        weight=2.0,
    )
    row = repository.add(db_session, payload)
    db_session.commit()
    assert row.id is not None
    assert row.name == "RAG"
    assert row.weight == 2.0
    assert repository.load_keywords(row) == ["rag", "검색 증강"]


def test_add_duplicate_name_raises(db_session):
    repository.add(db_session, InterestCreate(name="RAG", keywords=[]))
    db_session.commit()
    with pytest.raises(repository.InterestAlreadyExistsError):
        repository.add(db_session, InterestCreate(name="RAG", keywords=[]))


def test_list_filters_enabled(db_session):
    repository.add(db_session, InterestCreate(name="a", enabled=True))
    repository.add(db_session, InterestCreate(name="b", enabled=False))
    db_session.commit()
    all_rows = repository.list_interests(db_session)
    enabled = repository.list_interests(db_session, only_enabled=True)
    assert {r.name for r in all_rows} == {"a", "b"}
    assert {r.name for r in enabled} == {"a"}


def test_update_changes_fields_and_keywords(db_session):
    row = repository.add(
        db_session, InterestCreate(name="RAG", keywords=["rag"], weight=1.0)
    )
    db_session.commit()
    updated = repository.update(
        db_session,
        row.id,
        InterestUpdate(weight=3.0, keywords=["rag", "vector db"]),
    )
    db_session.commit()
    assert updated.weight == 3.0
    assert repository.load_keywords(updated) == ["rag", "vector db"]


def test_disable_sets_enabled_false(db_session):
    row = repository.add(db_session, InterestCreate(name="X"))
    db_session.commit()
    disabled = repository.disable(db_session, row.id)
    db_session.commit()
    assert disabled.enabled is False


def test_remove_drops_row(db_session):
    row = repository.add(db_session, InterestCreate(name="X"))
    db_session.commit()
    repository.remove(db_session, row.id)
    db_session.commit()
    assert repository.get(db_session, row.id) is None


def test_remove_missing_raises(db_session):
    with pytest.raises(repository.InterestNotFoundError):
        repository.remove(db_session, 999)


def test_load_keywords_tolerant_of_malformed_json(db_session):
    from newsletter.models.company_interest import CompanyInterest

    row = CompanyInterest(name="x", keywords_json="not json")
    db_session.add(row)
    db_session.commit()
    assert repository.load_keywords(row) == []


def test_set_embedding(db_session):
    row = repository.add(db_session, InterestCreate(name="X"))
    db_session.commit()
    repository.set_embedding(db_session, row.id, vector_bytes=b"\x01\x02", model="stub")
    db_session.commit()
    db_session.refresh(row)
    assert row.embedding == b"\x01\x02"
    assert row.embedding_model == "stub"
