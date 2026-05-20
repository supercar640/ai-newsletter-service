"""departments.repository — CRUD for the department registry."""

from __future__ import annotations

import pytest

from newsletter.slices.departments import repository
from newsletter.slices.departments.schemas import DepartmentCreate, DepartmentUpdate


def test_add_and_get(db_session):
    row = repository.add(
        db_session, DepartmentCreate(name="기획", description="제품/사업 기획")
    )
    db_session.commit()
    assert row.id is not None
    assert row.name == "기획"
    assert row.description == "제품/사업 기획"
    assert row.enabled is True


def test_add_duplicate_name_raises(db_session):
    repository.add(db_session, DepartmentCreate(name="영업"))
    db_session.commit()
    with pytest.raises(repository.DepartmentAlreadyExistsError):
        repository.add(db_session, DepartmentCreate(name="영업"))


def test_list_filters_enabled(db_session):
    repository.add(db_session, DepartmentCreate(name="a", enabled=True))
    repository.add(db_session, DepartmentCreate(name="b", enabled=False))
    db_session.commit()
    all_rows = repository.list_departments(db_session)
    enabled = repository.list_departments(db_session, only_enabled=True)
    assert {r.name for r in all_rows} == {"a", "b"}
    assert {r.name for r in enabled} == {"a"}


def test_update_changes_fields(db_session):
    row = repository.add(db_session, DepartmentCreate(name="마케팅"))
    db_session.commit()
    updated = repository.update(
        db_session, row.id, DepartmentUpdate(description="브랜드/퍼포먼스 마케팅")
    )
    assert updated.description == "브랜드/퍼포먼스 마케팅"


def test_disable_and_enable(db_session):
    row = repository.add(db_session, DepartmentCreate(name="관리"))
    db_session.commit()
    repository.disable(db_session, row.id)
    assert repository.get_or_raise(db_session, row.id).enabled is False
    repository.update(db_session, row.id, DepartmentUpdate(enabled=True))
    assert repository.get_or_raise(db_session, row.id).enabled is True


def test_remove(db_session):
    row = repository.add(db_session, DepartmentCreate(name="기술/설계"))
    db_session.commit()
    repository.remove(db_session, row.id)
    assert repository.get(db_session, row.id) is None


def test_get_or_raise_missing(db_session):
    with pytest.raises(repository.DepartmentNotFoundError):
        repository.get_or_raise(db_session, 999)
