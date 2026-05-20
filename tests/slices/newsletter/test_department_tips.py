"""department_tips — structured per-department tip generation + accumulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from newsletter.core.llm import LLMError
from newsletter.models.department import Department
from newsletter.models.newsletter_issue import NewsletterIssue
from newsletter.slices.newsletter.department_tips import (
    DepartmentTipItem,
    apply_department_tips,
    generate_department_tips,
    persist_department_tips,
    recent_tips_by_department,
    render_department_block,
)
from newsletter.slices.newsletter.practical import PracticalSection, PracticalUsecase


@dataclass
class _StubLLM:
    json_response: object = None
    raise_on: str | None = None
    json_calls: list[tuple[str, str]] = field(default_factory=list)

    def complete_json(self, body, *, model, max_tokens=1024):
        self.json_calls.append((body, model))
        if self.raise_on == "json":
            raise LLMError("stub fail")
        return (self.json_response, None)


def _depts(*names: str) -> list[Department]:
    return [Department(name=n, description=f"{n} 업무") for n in names]


def _usecase(title: str) -> PracticalUsecase:
    return PracticalUsecase(
        cluster_id="c1",
        title=title,
        scenario="s",
        method="m",
        prompt_example="p",
        caveats="c",
        sources=(),
    )


# --- generator -------------------------------------------------------------


def test_generate_returns_tip_per_department():
    llm = _StubLLM(
        json_response={
            "tips": [
                {"department": "기획", "tip": "기획 팁"},
                {"department": "영업", "tip": "영업 팁"},
            ]
        }
    )
    tips = generate_department_tips(
        [_usecase("회의록 요약")],
        _depts("기획", "영업"),
        {},
        date="2026-05-20",
        llm=llm,
    )
    assert tips == [
        DepartmentTipItem(department="기획", tip="기획 팁"),
        DepartmentTipItem(department="영업", tip="영업 팁"),
    ]


def test_generate_uses_sonnet_model():
    llm = _StubLLM(json_response={"tips": []})
    generate_department_tips(
        [_usecase("x")], _depts("기획"), {}, date="2026-05-20", llm=llm
    )
    assert llm.json_calls[0][1] == "claude-sonnet-4-6"


def test_generate_injects_recent_tips_into_prompt():
    llm = _StubLLM(json_response={"tips": []})
    generate_department_tips(
        [_usecase("x")],
        _depts("기획"),
        {"기획": ["지난주 썼던 팁"]},
        date="2026-05-20",
        llm=llm,
    )
    assert "지난주 썼던 팁" in llm.json_calls[0][0]


def test_generate_llm_failure_returns_empty():
    llm = _StubLLM(raise_on="json")
    tips = generate_department_tips(
        [_usecase("x")], _depts("기획"), {}, date="2026-05-20", llm=llm
    )
    assert tips == []


def test_generate_malformed_payload_returns_empty():
    llm = _StubLLM(json_response=["not", "a", "dict"])
    tips = generate_department_tips(
        [_usecase("x")], _depts("기획"), {}, date="2026-05-20", llm=llm
    )
    assert tips == []


def test_generate_skips_entries_missing_fields():
    llm = _StubLLM(
        json_response={"tips": [{"department": "기획"}, {"tip": "no dept"}]}
    )
    tips = generate_department_tips(
        [_usecase("x")], _depts("기획"), {}, date="2026-05-20", llm=llm
    )
    assert tips == []


# --- render ----------------------------------------------------------------


def test_render_block_lists_each_tip():
    block = render_department_block(
        [
            DepartmentTipItem(department="기획", tip="기획 팁"),
            DepartmentTipItem(department="영업", tip="영업 팁"),
        ]
    )
    assert "### 2. 부서별 활용 팁" in block
    assert "- 기획: 기획 팁" in block
    assert "- 영업: 영업 팁" in block


def test_render_block_empty_placeholder():
    block = render_department_block([])
    assert "### 2. 부서별 활용 팁" in block
    assert "이번 주 해당 내용 없음" in block


# --- accumulation (persist + recent) --------------------------------------


def _make_issue(db_session, *, title="x") -> NewsletterIssue:
    issue = NewsletterIssue(
        issue_date=date(2026, 5, 20), title=title, status="review_required"
    )
    db_session.add(issue)
    db_session.commit()
    db_session.refresh(issue)
    return issue


def test_persist_then_recent_returns_tips(db_session):
    issue = _make_issue(db_session)
    persist_department_tips(
        db_session,
        issue.id,
        [DepartmentTipItem(department="기획", tip="t1")],
    )
    db_session.commit()
    recent = recent_tips_by_department(db_session, ["기획"], limit_per_dept=4)
    assert recent == {"기획": ["t1"]}


def test_recent_is_newest_first_and_capped(db_session):
    for i in range(5):
        issue = _make_issue(db_session, title=f"i{i}")
        persist_department_tips(
            db_session, issue.id, [DepartmentTipItem(department="기획", tip=f"tip{i}")]
        )
        db_session.commit()
    recent = recent_tips_by_department(db_session, ["기획"], limit_per_dept=3)
    assert recent["기획"] == ["tip4", "tip3", "tip2"]


def test_recent_empty_for_unseen_department(db_session):
    recent = recent_tips_by_department(db_session, ["영업"], limit_per_dept=4)
    assert recent == {"영업": []}


# --- apply (splice §2 into the practical section) --------------------------

_SECTION_MD = """\
## B. 일반 임직원용 AI 활용 인사이트

### 1. 이번 주 바로 써볼 AI 활용법
- 활용법 본문

### 2. 부서별 활용 팁
- 기획: (작성기가 쓴 기존 한 줄)

### 3. 이번 주 추천 프롬프트
- 프롬프트

### 4. AI 사용 시 주의할 점
- 주의
"""


def _section() -> PracticalSection:
    return PracticalSection(markdown=_SECTION_MD, usecases=[_usecase("회의록 요약")])


def test_apply_splices_structured_block():
    llm = _StubLLM(
        json_response={"tips": [{"department": "기획", "tip": "신규 기획 팁"}]}
    )
    result = apply_department_tips(
        _section(), _depts("기획"), {}, date="2026-05-20", llm=llm
    )
    assert "- 기획: 신규 기획 팁" in result.markdown
    assert "(작성기가 쓴 기존 한 줄)" not in result.markdown
    # surrounding sections preserved
    assert "### 1. 이번 주 바로 써볼 AI 활용법" in result.markdown
    assert "### 3. 이번 주 추천 프롬프트" in result.markdown
    assert result.department_tips == [
        DepartmentTipItem(department="기획", tip="신규 기획 팁")
    ]


def test_apply_no_departments_returns_unchanged():
    llm = _StubLLM(json_response={"tips": []})
    section = _section()
    result = apply_department_tips(section, (), {}, date="2026-05-20", llm=llm)
    assert result.markdown == section.markdown
    assert result.department_tips == []


def test_apply_no_tips_keeps_writer_block():
    llm = _StubLLM(json_response={"tips": []})
    section = _section()
    result = apply_department_tips(
        section, _depts("기획"), {}, date="2026-05-20", llm=llm
    )
    assert "(작성기가 쓴 기존 한 줄)" in result.markdown
    assert result.department_tips == []
