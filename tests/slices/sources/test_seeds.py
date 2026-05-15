"""Seed idempotency tests."""

from __future__ import annotations

from sqlalchemy.orm import Session

from newsletter.slices.sources import repository, seeds


def test_seed_creates_expected_count(db_session: Session) -> None:
    created, updated = seeds.seed(db_session)
    db_session.commit()

    assert created == len(seeds.SEED_SOURCES)
    assert updated == 0
    assert len(repository.list_sources(db_session)) == len(seeds.SEED_SOURCES)


def test_seed_is_idempotent(db_session: Session) -> None:
    seeds.seed(db_session)
    db_session.commit()

    created, updated = seeds.seed(db_session)
    db_session.commit()

    assert created == 0
    assert updated == len(seeds.SEED_SOURCES)
    assert len(repository.list_sources(db_session)) == len(seeds.SEED_SOURCES)


def test_seed_covers_all_source_types(db_session: Session) -> None:
    seeds.seed(db_session)
    db_session.commit()

    types = {s.type for s in repository.list_sources(db_session)}
    assert {"NAVER_API", "RSS", "YOUTUBE_RSS"} <= types
