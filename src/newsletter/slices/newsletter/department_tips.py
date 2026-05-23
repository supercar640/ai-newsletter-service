"""Per-department usage tips (B-section §2): structured generation +
accumulation for duplicate-avoidance feedback.

A dedicated sonnet pass produces ``{department: tip}`` JSON, which is:
  * rendered deterministically into the ``### 2. 부서별 활용 팁`` block, and
  * persisted as :class:`DepartmentTip` rows so the next issue can feed recent
    tips back to the generator with a "don't repeat these" instruction.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from newsletter.core.llm import LLMClient, LLMError
from newsletter.core.logging import get_logger
from newsletter.core.prompts import load_prompt
from newsletter.models.department import Department
from newsletter.models.department_tip import DepartmentTip
from newsletter.slices.newsletter.practical import PracticalSection, PracticalUsecase

log = get_logger(__name__)

_TIPS_PROMPT = "practical-insight/practical-department-tips.md"


@dataclass(slots=True, frozen=True)
class DepartmentTipItem:
    """One generated department tip."""

    department: str
    tip: str


def generate_department_tips(
    usecases: Sequence[PracticalUsecase],
    departments: Sequence[Department],
    recent_tips_by_dept: Mapping[str, list[str]],
    *,
    date: str,
    llm: LLMClient,
) -> list[DepartmentTipItem]:
    """Generate one tip per department (sonnet). ``[]`` on any failure."""
    if not departments:
        return []

    prompt = load_prompt(_TIPS_PROMPT)
    body = prompt.render(
        date=date,
        departments_json=json.dumps(
            [{"name": d.name, "description": d.description or ""} for d in departments],
            ensure_ascii=False,
        ),
        usecases_json=json.dumps([_usecase_to_dict(u) for u in usecases], ensure_ascii=False),
        recent_tips_json=json.dumps(dict(recent_tips_by_dept), ensure_ascii=False),
    )
    try:
        payload, _ = llm.complete_json(body, model=prompt.model, max_tokens=1024)
    except LLMError as exc:
        log.warning("department_tips.generate.failed", error=str(exc))
        return []

    if not isinstance(payload, dict):
        log.warning("department_tips.generate.bad_payload", kind=type(payload).__name__)
        return []

    raw = payload.get("tips")
    if not isinstance(raw, list):
        return []

    out: list[DepartmentTipItem] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        department = str(entry.get("department") or "").strip()
        tip = str(entry.get("tip") or "").strip()
        if not department or not tip:
            continue
        out.append(DepartmentTipItem(department=department, tip=tip))
    return out


def render_department_block(tips: Sequence[DepartmentTipItem]) -> str:
    """Deterministic markdown for the ``### 2. 부서별 활용 팁`` block."""
    lines = ["### 2. 부서별 활용 팁"]
    if tips:
        lines.extend(f"- {t.department}: {t.tip}" for t in tips)
    else:
        lines.append("- 이번 주 해당 내용 없음")
    return "\n".join(lines)


# Matches the "### 2. 부서별 활용 팁" block up to (not including) the next
# "### " heading or end of string.
_SECTION2_RE = re.compile(
    r"###\s*2\.\s*부서별 활용 팁.*?(?=\n###\s|\Z)",
    re.DOTALL,
)


def apply_department_tips(
    section: PracticalSection,
    departments: Sequence[Department],
    recent_tips_by_dept: Mapping[str, list[str]],
    *,
    date: str,
    llm: LLMClient,
) -> PracticalSection:
    """Generate structured department tips and splice them into ``section``.

    Returns ``section`` unchanged when no departments are configured or the
    generator yields nothing — the writer's own §2 block is left intact.
    """
    if not departments:
        return section

    tips = generate_department_tips(
        section.usecases, departments, recent_tips_by_dept, date=date, llm=llm
    )
    if not tips:
        return section

    block = render_department_block(tips)
    # Trailing newline keeps the blank line before the following "### 3." heading.
    new_md, n = _SECTION2_RE.subn(block + "\n", section.markdown, count=1)
    if n == 0:
        log.warning("department_tips.splice.no_section2")
        return PracticalSection(
            markdown=section.markdown, usecases=section.usecases, department_tips=tips
        )
    return PracticalSection(markdown=new_md, usecases=section.usecases, department_tips=tips)


def persist_department_tips(
    session: Session,
    issue_id: int,
    tips: Sequence[DepartmentTipItem],
) -> None:
    """Store generated tips as DepartmentTip history rows (one per tip)."""
    for t in tips:
        session.add(DepartmentTip(issue_id=issue_id, department=t.department, tip=t.tip))
    session.flush()


def recent_tips_by_department(
    session: Session,
    department_names: Sequence[str],
    *,
    limit_per_dept: int = 4,
) -> dict[str, list[str]]:
    """Most-recent tips per department, newest first, capped per department."""
    result: dict[str, list[str]] = {}
    for name in department_names:
        rows = session.scalars(
            select(DepartmentTip)
            .where(DepartmentTip.department == name)
            .order_by(DepartmentTip.id.desc())
            .limit(limit_per_dept)
        ).all()
        result[name] = [r.tip for r in rows]
    return result


def _usecase_to_dict(u: PracticalUsecase) -> dict[str, object]:
    return {
        "title": u.title,
        "scenario": u.scenario,
        "method": u.method,
        "caveats": u.caveats,
    }


__all__ = [
    "DepartmentTipItem",
    "apply_department_tips",
    "generate_department_tips",
    "persist_department_tips",
    "recent_tips_by_department",
    "render_department_block",
]
