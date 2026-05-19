"""CompanyInterest model tests (Phase 2 — company-interest scoring)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from newsletter.models.company_interest import CompanyInterest


def test_minimal_insert_defaults(db_session):
    interest = CompanyInterest(
        name="RAG",
        keywords_json='["rag", "검색 증강"]',
    )
    db_session.add(interest)
    db_session.commit()
    db_session.refresh(interest)
    assert interest.id is not None
    assert interest.weight == 1.0
    assert interest.enabled is True
    assert interest.description is None
    assert interest.embedding is None
    assert interest.embedding_model is None
    assert interest.created_at is not None


def test_name_is_unique(db_session):
    db_session.add(CompanyInterest(name="RAG", keywords_json="[]"))
    db_session.commit()
    db_session.add(CompanyInterest(name="RAG", keywords_json="[]"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_weight_can_be_set(db_session):
    interest = CompanyInterest(
        name="AI 영업",
        keywords_json="[]",
        description="영업/마케팅 자동화 관련 AI 사용 사례",
        weight=2.5,
    )
    db_session.add(interest)
    db_session.commit()
    db_session.refresh(interest)
    assert interest.weight == 2.5
    assert interest.description == "영업/마케팅 자동화 관련 AI 사용 사례"


def test_disabled_flag_persists(db_session):
    interest = CompanyInterest(name="legacy topic", keywords_json="[]", enabled=False)
    db_session.add(interest)
    db_session.commit()
    db_session.refresh(interest)
    assert interest.enabled is False


def test_embedding_blob_roundtrip(db_session):
    payload = bytes([1, 2, 3, 4])
    interest = CompanyInterest(
        name="vec",
        keywords_json="[]",
        embedding=payload,
        embedding_model="stub",
    )
    db_session.add(interest)
    db_session.commit()
    db_session.refresh(interest)
    assert interest.embedding == payload
    assert interest.embedding_model == "stub"
