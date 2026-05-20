# 260520 핸드오프 — Phase 2 완료 (Slack 요약 발송 + 부서별 활용 팁 개선)

> Human-in-the-loop 작업 정리 노트. 다음 세션이 끊김 없이 이어갈 수 있도록 합니다.
> 진실 공급원: `plan/ai_newsletter_service_plan.md`, 승인 플랜 `C:\Users\user\.claude\plans\wondrous-cooking-quill.md`.

---

## 한 줄 요약

이번 세션에서 Phase 2의 마지막 두 항목 — **Slack 요약 발송**과 **부서별 활용 팁
개선** — 을 브레인스토밍 → 설계 문서 → TDD 구현 흐름으로 완료했습니다. 이로써
**Phase 1(MVP) + Phase 2(품질 개선) 6개 항목이 모두 끝났습니다.** 전체 테스트
502개 통과, 워킹 트리 클린.

---

## 이번 세션에서 완료한 작업

### 1. Slack 요약 카드 발송 (commit `7d6845b`)

이메일과 **독립된 배포 채널**. 승인된 이슈를 Slack Incoming Webhook으로 요약
카드(Block Kit)로 발송. 추가 LLM 없이 본문에서 결정적으로 하이라이트 추출.

산출물:
- `src/newsletter/slices/distribution/card.py` — 이슈 → Block Kit 카드(순수 함수).
  본문의 `#### ` 헤드라인 추출(최대 5) + Notion 아카이브 링크 버튼(있을 때).
- `src/newsletter/slices/distribution/slack_client.py` — httpx 기반 webhook 래퍼.
  `from_settings()` 미설정 시 `None` 폴백(Notion 패턴 동일).
- `src/newsletter/slices/distribution/slack.py` — `approved` 가드 + `slack_sent_at`
  멱등(`--force`). **상태 전환 없음** — `sent` 전환은 이메일 발송이 소유.
- `src/newsletter/slices/distribution/cli.py` — `slack` 서브커맨드 추가.
- 모델 `NewsletterIssue.slack_sent_at` 컬럼 + 마이그레이션 `f5662d6e7ec4`.
- 설정 `SLACK_WEBHOOK_URL`, `.env.example` / `AGENTS.md` 갱신.
- 설계 문서 `docs/superpowers/specs/2026-05-20-slack-summary-card-design.md`.

테스트 26개 추가(card 8 / client 6 / service 6 / cli 6).

### 2. 부서별 활용 팁 개선 (commit `ba4cdfc`)

B섹션 §2 "부서별 활용 팁"을 **부서 레지스트리 + 사례 축적 + 중복 회피**로 개선.

산출물:
- `src/newsletter/slices/departments/` — Department 레지스트리(model/repo/schemas/
  cli/seeds), `interests` 슬라이스 미러. 시드: 기획·영업·마케팅·기술/설계·관리.
- `src/newsletter/models/department_tip.py` — (이슈×부서)당 1행 이력. 부서명을
  문자열로 비정규화 저장(레지스트리 삭제가 이력을 깨지 않게).
- `src/newsletter/slices/newsletter/department_tips.py`:
  - `generate_department_tips` — 전용 **sonnet** 패스, `{부서: 팁}` 구조화 JSON.
    최근 팁을 "반복 금지"로 주입(중복 회피 되먹임). 실패 시 빈 리스트 폴백.
  - `render_department_block` — §2 마크다운 결정적 렌더.
  - `apply_department_tips` — 작성기 §2 블록을 구조화 팁으로 splice(후처리 래퍼).
  - `persist_department_tips` / `recent_tips_by_department` — 영속화·최근 조회.
- 프롬프트 `prompts/practical-insight/practical-department-tips.md` (sonnet).
- `assembler.draft_issue` 통합: 활성 부서 + 최근 팁 로드 → apply → 이슈 생성 후
  영속화. **부서 미등록 시 완전 no-op(회귀 0).**
- 마이그레이션 `27b382d1bde7` (departments, department_tips). `AGENTS.md` 갱신.
- 설계 문서 `docs/superpowers/specs/2026-05-20-department-tips-design.md`.

테스트 32개 추가(repo 7 / seeds 2 / cli 6 / department_tips 14 / assembler 통합 3).

### 검증 상태(세션 종료 시점)

- `uv run pytest` → **502/502 통과**
- `uv run ruff check` (신규/수정 파일) → 통과
- Alembic head = `27b382d1bde7` (dev DB 적용 완료)
- 워킹 트리 클린, 모두 커밋됨

---

## 주의/메모 (비자명한 결정)

- **CLI 서브커맨드 중첩**: `newsletter send`·`newsletter slack`은 단일 명령 Typer
  앱을 루트에 마운트한 구조라 실제 호출은 `newsletter send send` / `newsletter
  slack slack` 입니다. AGENTS 표기는 collapse된 형태(실제와 불일치). 단일 형태를
  원하면 `invoke_without_command` 콜백으로 평탄화하는 별도 리팩터 필요.
- **ruff format 전역 드리프트**: 기존 코드베이스가 현재 ruff line-length보다 짧게
  wrap돼 있어, `uv run ruff format`을 통째로 돌리면 무관한 파일 20여 개가 함께
  재포맷됩니다. 커밋엔 변경 파일만 골라 `ruff check --fix <files>`로 처리했고
  전역 format은 피했습니다. (별도 정리 PR로 한 번에 포맷 통일하는 것은 마스터
  판단.)
- **부서별 팁 통합은 additive**: `build_practical_section`과 작성기 프롬프트는
  무변경. 설계 문서엔 시그니처 변경으로 적었으나 회귀 위험 0인 후처리 래퍼
  `apply_department_tips`로 분리했습니다.

---

## Phase 진행 상황

플랜 §25 기준.

- **Phase 1 (MVP)**: 완료 (Iteration 1~11).
- **Phase 2 (품질 개선)**: 6개 전부 완료.
  1. 중요도 스코어링(회사 관심사) — interests
  2. 임베딩 기반 중복 제거 — Voyage(voyage-3-lite), 키 없으면 Jaccard 폴백
  3. 뉴스레터 템플릿 다양화 — audiences(general/executive/technical)
  4. Notion 아카이브 — archive
  5. **Slack 요약 발송** — distribution.slack (이번 세션)
  6. **부서별 활용 팁 개선** — departments + department_tips (이번 세션)
- **Phase 3 (고도화)**: 미착수.

---

## 다음 세션에 이어서 할 일 (Phase 3 후보)

플랜 §25 Phase 3 표에서:

- [ ] **회사 관심사 RAG** — 내부 키워드·프로젝트 기준을 RAG로 반영
      (현재 interests는 키워드 + 임베딩 코사인까지. 사내 문서 기반 RAG로 확장).
- [ ] **트렌드 분석** — 주간/월간 변화 추적(누적 ProcessedItem/이슈 기반).
- [ ] **경쟁사 모니터링** — 특정 기업/제품 추적(소스/스코어링 확장).
- [ ] **자동 월간 리포트** — 월간 AI 동향 보고서 자동 생성.
- [ ] **성과 대시보드** — 소스별 성과, 클릭률, 품질 지표(검수 UI/모니터링 확장).
- [ ] **부서별 맞춤 뉴스레터** — 독자 그룹별 콘텐츠 자동 구성
      (이번에 만든 departments 레지스트리를 발송 분기까지 확장 — 단 스펙 §10에서
      "초기엔 통합본으로 충분"이라 했으므로 우선순위 재확인 필요).

### 권장 다음 단계

각 항목은 독립적이므로 마스터가 우선순위를 정해 하나를 골라 브레인스토밍으로
시작하면 됩니다. 새 기능은 이번 세션과 동일하게:
1. 브레인스토밍(질문 → 설계안)
2. `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` 설계 문서 커밋
3. TDD(실패 테스트 → 최소 구현 → 통과 → 커밋)

흐름을 따릅니다.

### 잔여 정리(선택)

- [ ] CLI 단일 명령 평탄화(`newsletter slack ...` 직접 호출) — UX 개선, 별도 리팩터.
- [ ] ruff format 전역 통일 PR — 코드베이스 포맷 드리프트 해소.

---

## 주요 파일 경로

| 종류 | 경로 |
|------|------|
| 스펙 | `plan/ai_newsletter_service_plan.md` |
| 승인 플랜 | `C:\Users\user\.claude\plans\wondrous-cooking-quill.md` |
| 설계 문서 | `docs/superpowers/specs/2026-05-20-slack-summary-card-design.md`, `docs/superpowers/specs/2026-05-20-department-tips-design.md` |
| 공통 에이전트 가이드 | `AGENTS.md` |
| 핸드오프 노트 | `hitl/260520-phase2-완료-slack발송-부서별팁.md` (본 문서) |

---

## 세션 끝 시점 상태

- Git: `main` 브랜치, working tree clean, 마지막 커밋 `ba4cdfc`.
- 테스트: 502/502 통과. 린트: 통과.
- 미커밋: 본 문서 하나만 신규 — 다음 세션 시작 시 추가/커밋 결정.

수고하셨습니다. 다음 세션에서 Phase 3로 이어가겠습니다.
