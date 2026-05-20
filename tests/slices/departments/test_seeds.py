"""departments.seeds — idempotent seed of the default org units."""

from __future__ import annotations

from newsletter.slices.departments import repository
from newsletter.slices.departments.seeds import SEED_DEPARTMENTS, seed


def test_seed_creates_default_departments(db_session):
    created, updated = seed(db_session)
    db_session.commit()
    names = {d.name for d in repository.list_departments(db_session)}
    assert {"기획", "영업", "마케팅", "기술/설계", "관리"} <= names
    assert created == len(SEED_DEPARTMENTS)
    assert updated == 0


def test_seed_is_idempotent(db_session):
    seed(db_session)
    db_session.commit()
    created, updated = seed(db_session)
    db_session.commit()
    assert created == 0
    assert updated == len(SEED_DEPARTMENTS)
    # no duplicates
    names = [d.name for d in repository.list_departments(db_session)]
    assert len(names) == len(set(names))
