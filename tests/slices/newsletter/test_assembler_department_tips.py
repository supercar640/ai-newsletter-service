"""Assembler + department-tips integration (Phase 2).

When departments are registered, draft_issue runs the dedicated tips pass,
splices the structured §2 block into the practical section, and persists the
tips so the next issue can feed them back as "avoid repeating".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls

from sqlalchemy import select

from newsletter.core.llm import LLMResponse
from newsletter.models.department_tip import DepartmentTip
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.departments import repository as dept_repo
from newsletter.slices.departments.schemas import DepartmentCreate
from newsletter.slices.newsletter.assembler import draft_issue

TODAY = date_cls(2026, 5, 18)


@dataclass
class _StubLLM:
    """Returns a tips payload for the dept-tips prompt, usecase fields otherwise."""

    usecase_payload: dict = field(
        default_factory=lambda: {
            "title": "스텁",
            "summary": "요약",
            "why_it_matters": "중요",
            "company_perspective": "관점",
            "scenario": "시나리오",
            "method": "방법",
            "prompt_example": "프롬프트",
            "caveats": "주의",
            "sources": [],
        }
    )
    tip_text: str = "기획 신규 팁"
    json_calls: list[str] = field(default_factory=list)

    def complete_json(self, body, *, model, max_tokens=1024):
        self.json_calls.append(body)
        if "부서별 활용 팁" in body:
            return ({"tips": [{"department": "기획", "tip": self.tip_text}]}, None)
        return (self.usecase_payload, None)

    def complete(self, body, *, model, max_tokens=4096, system=None, temperature=0.2):
        return LLMResponse(text="opus", model=model, input_tokens=0, output_tokens=0)


def _seed_dept(db_session):
    dept_repo.add(db_session, DepartmentCreate(name="기획", description="기획 업무"))
    db_session.commit()


def test_draft_persists_and_splices_department_tips(db_session):
    _seed_dept(db_session)
    llm = _StubLLM()
    report = draft_issue(db_session, today=TODAY, llm=llm)
    db_session.commit()

    issue = db_session.get(NewsletterIssue, report.issue_id)
    assert "- 기획: 기획 신규 팁" in issue.practical_section_md
    assert "- 기획: 기획 신규 팁" in issue.markdown_body

    tips = list(db_session.scalars(select(DepartmentTip)).all())
    assert len(tips) == 1
    assert tips[0].department == "기획"
    assert tips[0].tip == "기획 신규 팁"
    assert tips[0].issue_id == issue.id


def test_disabled_department_is_skipped(db_session):
    dept_repo.add(
        db_session, DepartmentCreate(name="기획", description="x", enabled=False)
    )
    db_session.commit()
    llm = _StubLLM()
    draft_issue(db_session, today=TODAY, llm=llm)
    db_session.commit()

    tips = list(db_session.scalars(select(DepartmentTip)).all())
    assert tips == []
    # No dept-tips prompt was issued.
    assert all("부서별 활용 팁" not in b for b in llm.json_calls)


def test_prior_tips_are_fed_back_as_recent(db_session):
    _seed_dept(db_session)
    first = _StubLLM(tip_text="첫 주 팁")
    draft_issue(db_session, today=TODAY, llm=first)
    db_session.commit()

    second = _StubLLM(tip_text="둘째 주 팁")
    draft_issue(db_session, today=date_cls(2026, 5, 25), llm=second)
    db_session.commit()

    dept_bodies = [b for b in second.json_calls if "부서별 활용 팁" in b]
    assert dept_bodies
    assert "첫 주 팁" in dept_bodies[0]
