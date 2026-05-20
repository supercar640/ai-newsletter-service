# 부서별 활용 팁 개선 — 설계

> Phase 2 항목 "부서별 활용 팁 개선 / 부서별 실무 사례 축적"
> (`plan/ai_newsletter_service_plan.md` §25, §2, §8.2 B.2).
> 작성일: 2026-05-20. 상태: 승인됨.

## 목적

뉴스레터 B섹션 §2 "부서별 활용 팁"을 개선한다. 현재는 opus 작성기가 고정
부서(기획·영업·마케팅·기술/설계·관리)에 대해 그 주 usecase에서 즉석으로 한 줄씩
생성하며, 부서 설정도 과거 사례 축적도 없다. 이를 (1) 설정 가능한 부서
레지스트리, (2) 부서별 팁 영속화·축적, (3) 최근 팁 되먹임을 통한 중복 회피로
개선한다.

## 범위 결정 (브레인스토밍 합의)

- **핵심 산출물**: 부서 레지스트리 + 사례 축적.
- **축적 활용**: 중복 회피 되먹임 — 다음 호 작성 시 부서별 최근 N개 팁을
  생성 프롬프트에 "반복 금지"로 주입.
- **생성 방식**: §2 부서별 팁을 전용 sonnet 패스로 분리해 구조화 JSON으로
  생성·영속화. 메인 작성기는 그대로 두고 후처리로 §2 블록 치환.
- **제외(YAGNI)**: 부서 누적 프로필/개인화, 부서별 분기 발송(Phase 3).

## 아키텍처

### 1. 새 슬라이스 `departments` (레지스트리, `interests` 미러)

```
src/newsletter/slices/departments/
  __init__.py, repository.py, schemas.py, cli.py, seeds.py
models/department.py
```

`Department` 모델: `id`, `name`(unique), `description`(업무 특성, 프롬프트 컨텍스트),
`enabled`, `created_at`. CompanyInterest의 최소 미러(임베딩/weight/keywords 제외).

- repository: `list_departments(only_enabled=)`, `add`, `update`, `disable`,
  `enable`, `remove`, `get_or_raise` — interests repo 미러. 중복 이름은
  `DepartmentAlreadyExistsError`.
- CLI `newsletter departments`: list / add / disable / enable / remove / seed.
- seeds: 기획 · 영업 · 마케팅 · 기술/설계 · 관리 (스펙 §8.2 형식과 일치). 멱등.

### 2. 축적 모델 `DepartmentTip`

```
models/department_tip.py
```

`id`, `issue_id`(FK `newsletter_issues.id`), `department`(String, 비정규화),
`tip`(Text), `created_at`. `Index(department, created_at)` — 최근 조회용.

부서명을 문자열로 비정규화 저장하여 레지스트리 변경/삭제가 과거 이력을 깨지
않게 한다. 부서×이슈당 1행.

### 3. 전용 구조화 패스 `slices/newsletter/department_tips.py`

- 프롬프트 `prompts/practical-insight/practical-department-tips.md` (**sonnet**).
  - frontmatter inputs: `date, departments_json, usecases_json, recent_tips_json`.
  - output_schema: `{"tips": [{"department": str, "tip": str}]}`.
  - 지시: 부서 업무 특성 + 이번 주 usecase 근거로 부서별 한 줄 팁. 환각 금지.
    `recent_tips_json`에 있는 최근 팁은 **반복 금지**(중복 회피).
- `DepartmentTipItem` dataclass: `department`, `tip`.
- `generate_department_tips(usecases, departments, recent_tips_by_dept, *, date, llm)`
  → `list[DepartmentTipItem]`. LLM 실패 / malformed → 빈 리스트 폴백.
- `render_department_block(tips) -> str` — `### 2. 부서별 활용 팁` 마크다운
  결정적 렌더. 팁 없으면 "- 이번 주 해당 내용 없음".

### 4. 통합 (additive — 기존 동작 보존)

`build_practical_section(briefs, *, date, llm, departments=(), recent_tips_by_dept=None)`:

- `departments`가 비면 **기존과 100% 동일** 동작 (기존 테스트 무수정 통과).
- 부서가 주어지면:
  1. usecases 요약 (기존 sonnet)
  2. `generate_department_tips(...)` (신규 sonnet)
  3. 작성기 §1~§4 마크다운 (기존 opus)
  4. 후처리: `### 2.`~`### 3.` 구간을 `render_department_block` 결과로 치환.
     팁이 0개면 치환 생략(작성기 §2 유지).
- `PracticalSection`에 `department_tips: list[DepartmentTipItem]` 필드 추가
  (`field(default_factory=list)`).

sonnet/opus 구분은 기존대로 프롬프트 frontmatter `model`로 라우팅 — `llm`
클라이언트 하나를 그대로 넘긴다.

**assembler `draft_issue`**:
- 섹션 빌드 전 `list_departments(only_enabled=True)` + 부서별 최근 팁 로드.
- `recent_tips_by_department(session, departments, limit_per_dept=4)` (기본 4개 이슈분).
- `build_practical_section(...)`에 전달.
- 이슈 생성·flush **후** `persist_department_tips(session, issue_id, tips)`로
  `DepartmentTip` 행 영속화 (부서당 1행).

### 5. 마이그레이션

Alembic autogenerate — `departments`, `department_tips` 테이블 추가.

## 테스트 (TDD, 실제 외부 호출 없음)

- `departments` repository: CRUD / 중복 이름 거부 / only_enabled 필터 (interests 미러).
- `departments` seeds: 멱등 (재실행 시 갱신).
- `departments` CLI: list / add / disable / remove (fake session_scope).
- `department_tips` generator (fake LLM): 부서별 팁 생성 / recent_tips가
  프롬프트에 주입됨 / LLM 실패 폴백 빈 리스트 / 렌더 블록 형식.
- `recent_tips_by_department`: 부서별 최근 N개, 최신순.
- `build_practical_section`: 부서 주어질 때 §2 치환 / 미주어 시 회귀 동일 /
  `department_tips` 반환.
- assembler: 영속화 1행/부서 / 다음 draft가 직전 팁을 recent로 받음(통합).

## 미적용 (YAGNI)

- 부서 누적 프로필 / 부서별 개인화 콘텐츠.
- 부서별 분기 발송 (Phase 3).
- Department 임베딩 / 키워드 매칭.
