"""interests CLI smoke tests."""

from __future__ import annotations

from typer.testing import CliRunner

from newsletter.slices.interests import repository
from newsletter.slices.interests.cli import app
from newsletter.slices.interests.schemas import InterestCreate

runner = CliRunner()


def test_list_empty(db_session):
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "no interests registered" in result.output


def test_add_creates_row(db_session):
    result = runner.invoke(
        app,
        ["add", "--name", "RAG", "--keywords", "rag,vector db", "--weight", "2.0"],
    )
    assert result.exit_code == 0, result.output
    assert "interest 추가 완료" in result.output

    rows = repository.list_interests(db_session)
    db_session.expire_all()
    rows = repository.list_interests(db_session)
    assert len(rows) == 1
    assert rows[0].name == "RAG"
    assert rows[0].weight == 2.0


def test_add_duplicate_name_exits_nonzero(db_session):
    repository.add(db_session, InterestCreate(name="RAG"))
    db_session.commit()
    result = runner.invoke(app, ["add", "--name", "RAG"])
    assert result.exit_code != 0


def test_disable_and_enable_round_trip(db_session):
    row = repository.add(db_session, InterestCreate(name="RAG"))
    db_session.commit()
    rid = row.id

    r1 = runner.invoke(app, ["disable", str(rid)])
    assert r1.exit_code == 0
    db_session.expire_all()
    assert repository.get(db_session, rid).enabled is False

    r2 = runner.invoke(app, ["enable", str(rid)])
    assert r2.exit_code == 0
    db_session.expire_all()
    assert repository.get(db_session, rid).enabled is True


def test_remove(db_session):
    from sqlalchemy import select

    from newsletter.models.company_interest import CompanyInterest

    row = repository.add(db_session, InterestCreate(name="RAG"))
    db_session.commit()
    rid = row.id
    result = runner.invoke(app, ["remove", str(rid)])
    assert result.exit_code == 0
    db_session.expire_all()
    leftover = db_session.scalars(
        select(CompanyInterest).where(CompanyInterest.id == rid)
    ).first()
    assert leftover is None


def test_list_renders_keywords(db_session):
    repository.add(
        db_session,
        InterestCreate(name="RAG", keywords=["rag", "vector"], weight=1.5),
    )
    db_session.commit()
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "RAG" in result.output
    assert "rag" in result.output
    assert "1.50" in result.output
