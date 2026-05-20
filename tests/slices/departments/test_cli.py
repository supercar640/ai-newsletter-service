"""departments CLI smoke tests."""

from __future__ import annotations

from typer.testing import CliRunner

from newsletter.slices.departments import repository
from newsletter.slices.departments.cli import app
from newsletter.slices.departments.schemas import DepartmentCreate

runner = CliRunner()


def test_list_empty(db_session):
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "no departments registered" in result.output


def test_add_creates_row(db_session):
    result = runner.invoke(
        app, ["add", "--name", "기획", "--description", "제품 기획"]
    )
    assert result.exit_code == 0, result.output
    db_session.expire_all()
    rows = repository.list_departments(db_session)
    assert len(rows) == 1
    assert rows[0].name == "기획"


def test_add_duplicate_exits_nonzero(db_session):
    repository.add(db_session, DepartmentCreate(name="기획"))
    db_session.commit()
    result = runner.invoke(app, ["add", "--name", "기획"])
    assert result.exit_code != 0


def test_disable_round_trip(db_session):
    row = repository.add(db_session, DepartmentCreate(name="영업"))
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
    row = repository.add(db_session, DepartmentCreate(name="마케팅"))
    db_session.commit()
    rid = row.id
    result = runner.invoke(app, ["remove", str(rid)])
    assert result.exit_code == 0
    db_session.expire_all()
    assert repository.get(db_session, rid) is None


def test_seed_command(db_session):
    result = runner.invoke(app, ["seed"])
    assert result.exit_code == 0, result.output
    db_session.expire_all()
    names = {d.name for d in repository.list_departments(db_session)}
    assert {"기획", "영업", "마케팅", "기술/설계", "관리"} <= names
