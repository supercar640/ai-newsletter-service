"""Default department seeds (spec §8.2 부서별 활용 팁 format).

Idempotent: re-running ``newsletter departments seed`` updates existing rows
(by name) in place rather than failing.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from newsletter.slices.departments import repository
from newsletter.slices.departments.schemas import DepartmentCreate, DepartmentUpdate

SEED_DEPARTMENTS: list[DepartmentCreate] = [
    DepartmentCreate(name="기획", description="제품·사업 기획, 전략, 시장 분석"),
    DepartmentCreate(name="영업", description="고객 발굴, 제안, 계약, 매출 관리"),
    DepartmentCreate(name="마케팅", description="브랜드, 콘텐츠, 퍼포먼스 마케팅"),
    DepartmentCreate(name="기술/설계", description="엔지니어링, 설계, 개발 실무"),
    DepartmentCreate(name="관리", description="경영지원, 인사, 재무, 총무"),
]


def seed(session: Session) -> tuple[int, int]:
    """Apply seed data. Returns ``(created, updated)``."""
    existing = {d.name: d for d in repository.list_departments(session)}
    created = updated = 0
    for payload in SEED_DEPARTMENTS:
        row = existing.get(payload.name)
        if row is None:
            repository.add(session, payload)
            created += 1
        else:
            repository.update(session, row.id, DepartmentUpdate(description=payload.description))
            updated += 1
    return created, updated
