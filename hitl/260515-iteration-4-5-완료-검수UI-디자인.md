# 260515 핸드오프 — Iteration 4·5 완료, 검수 UI 방향 결정 + Pencil 디자인

> Human-in-the-loop 작업 정리 노트. 이 문서는 다음 세션이 끊김 없이 이어서 작업할 수 있도록 합니다.
> 진실 공급원: `plan/ai_newsletter_service_plan.md`, 승인 플랜은 `C:\Users\user\.claude\plans\wondrous-cooking-quill.md`.

---

## 한 줄 요약

이번 세션에서 백엔드는 **Iteration 4(통합·후보선정)** 와 **Iteration 5(전문가 트랙 작성기)** 까지 완료했고, 마스터가 결정한 대로 **검수 UI를 FastAPI + Jinja2 + Pencil 디자인**으로 가기로 했습니다. Pencil 디자인 파일과 3장의 화면 시안이 준비됐고, 아직 코드 구현은 시작 전입니다.

---

## 지금까지 완료된 작업

### Iteration 4 — Integration (commit `ab1b57d`)

산출물:
- `src/newsletter/slices/integration/scoring.py` — `trust × recency 감쇠` 기반 베이스 점수 + 상위 K건 LLM 부스트(0.5~1.5x). 결과를 `ProcessedItem.importance_score`에 영속화.
- `src/newsletter/slices/integration/clustering.py` — `duplicate_group_id` 시드 + 제목 토큰 Jaccard 0.5 union-find. 임베딩 교체 포인트가 `_jaccard()`로 분리되어 있음.
- `src/newsletter/slices/integration/candidates.py` — 클러스터당 대표 1건 → 트랙별 top-N(전문가 7 / 일반 4 기본) + 카테고리 다양성 soft cap.
- `src/newsletter/slices/integration/service.py` — ProcessedItem ↔ RawItem ↔ Source 조인 → 점수 → 클러스터 → 후보 선정 오케스트레이션.
- `src/newsletter/slices/integration/cli.py` — `newsletter integrate [--no-llm] [--expert-count N] [--practical-count N]`.
- `prompts/expert-news/expert-importance-scorer.md` — 1-5점 JSON 출력 (sonnet).

테스트 61개 추가.

### Iteration 5 — Expert Section Pipeline (commit `c178c65`)

산출물:
- `prompts/expert-news/expert-cluster-summarizer.md` — 클러스터 → `{title, summary, why_it_matters, company_perspective, sources}` JSON (sonnet).
- `prompts/expert-news/expert-news-writer.md` — 클러스터 요약 배열 → 스펙 §8.2 A섹션 한국어 마크다운 (opus).
- `src/newsletter/slices/newsletter/expert.py`:
  - `summarize_cluster`, `summarize_clusters` — sonnet 패스. LLM 실패/malformed JSON 은 해당 클러스터 스킵.
  - `write_expert_section` — opus 패스. 빈 입력 short-circuit; LLM 실패 시 결정적 로컬 템플릿 폴백.
  - `build_expert_section` — 풀 파이프라인.

테스트 16개 추가.

### 검증 상태(세션 종료 시점)

- `uv run pytest` → **225/225 통과**
- `uv run ruff check .` → **All checks passed**
- 작업 디렉토리 변경 없음(모두 커밋됨).

---

## 검수 UI 결정 사항

### 결정한 것

- **백엔드 프레임워크**: **FastAPI + Jinja2 SSR** (Next.js 거부, Streamlit 거부)
  - 이유: Python 단일 스택 유지, 모듈러 모놀리스 구조 보존, 사내 관리자 1~소수 전제.
  - HTMX 로 부분 갱신은 도입 후보(아직 미결정).
- **디자인 도구**: Pencil (`.pen`) 파일.
  - 파일: `design/newsletter_admin.pen` (이번에 신규 생성).

### 화면 구성

| # | 화면 | 핵심 요소 |
|---|------|----------|
| 1 | Dashboard | 사이드바 + 파이프라인 StatCard 4개(수집/처리/후보/검수대기) + 최근 이슈 테이블 + "오늘자 이슈 검수 시작" CTA |
| 2 | Issue Review | 좌: 후보 선택 패널(전문가/일반, 체크박스 토글). 우: 마크다운 미리보기. 상단: 임시저장/거절/승인 |
| 3 | Send Confirm | 이슈 요약 + 드라이런 토글 + 발신/수신자 목록 + 경고 배너 + 발송 액션 |

### FastAPI 라우트 골자(미구현, 다음 세션에 만듭니다)

```
GET  /                           → Dashboard
GET  /issues/{id}                → Issue Review
POST /issues/{id}/toggle         → 후보 in/out 토글 (HTMX 부분 갱신 후보)
POST /issues/{id}/regenerate     → 선택분으로 초안 재생성
POST /issues/{id}/approve        → 상태 approved 로 전환
GET  /issues/{id}/send           → Send Confirm
POST /issues/{id}/send           → 실제 발송 (dry-run 옵션)
```

---

## Pencil 디자인 자산(`design/newsletter_admin.pen`)

### 등록된 디자인 토큰(35개)

- 색: accent-primary `#2563EB` / success `#16A34A` / warning `#D97706` / danger `#DC2626`, plus surface/border/text/sidebar variants.
- 타이포: `Inter`(body, heading) + `Geist Mono`(숫자/타임스탬프).
- 스페이싱: `--space-1` ~ `--space-12` (4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48).
- 코너: `--radius-sm/md/lg` (4 / 6 / 8).

### 재사용 컴포넌트(17개+)

- `Button/Primary, Secondary, Danger, Ghost`
- `Badge/Green, Yellow, Red, Neutral, Info` (이슈 라이프사이클 상태 표시용)
- `Card, StatCard, StatCard/Danger`
- `Input/Text, Checkbox/Unchecked, Checkbox/Checked`
- `SideNavItem, SideNavItem/Active`
- `Table/HeaderRow, Table/BodyRow`
- **`CandidateRow`** — 뉴스레터 특화. 체크박스 + 제목 + 메타(출처·카테고리·시간) + 중요도 점수.

### 화면 노드 ID 메모

- Design System frame: `o9Nd9` (위치 (80, 80))
- Screen 1 Dashboard: `OAcZz` (1380, 80, 1440×900) — **시각 검증 완료**
- Screen 2 Issue Review: `HcTpg` (1380, 1080, 1440×1400) — 구조 OK, 시각 미러닝 이슈 있음(아래 참조)
- Screen 3 Send Confirm: `UgtHK` (1380, 2300, 1440×1100) — 구조 OK, 시각 미러닝 이슈 있음

### 알려진 Pencil 렌더러 이슈

- nested fit_content 프레임 안에 ref 노드를 여러 개 넣을 때 vertical layout 계산이 깨지는 버그를 만남.
- `get_screenshot` 이 Screen 2·3 에서 일부/전부 비어 보이지만 `snapshot_layout` 으로 보면 자식들이 모두 존재함.
- HTML/CSS 구현에서는 이 버그가 없음(Pencil 한정). 디자인 의도는 명확하므로 다음 세션에서 HTML 구축 시 그대로 옮기면 됩니다.

---

## 다음 세션에 이어서 할 일

### 우선순위 1 — 검수 UI 구현(이번 세션의 자연스러운 후속)

- [ ] FastAPI 의존성 추가: `uv add fastapi uvicorn jinja2 python-multipart`.
- [ ] `src/newsletter/admin/` 슬라이스 신설(라우트 + 템플릿 + 정적 자산).
- [ ] Pencil 디자인 토큰을 `static/css/tokens.css` 로 옮기기(get_variables 결과 그대로 CSS 변수화).
- [ ] 컴포넌트를 Jinja2 매크로로 1:1 포팅(`{% macro button() %}` 등).
- [ ] Dashboard 라우트 먼저 — 실 DB(StatCards + 최근 이슈 테이블) 연결, 골든 패스 동작 확인.
- [ ] Issue Review — 후보 토글 핸들러, 마크다운 렌더(`markdown-it-py` 후보).
- [ ] Send Confirm — `dry-run` 옵션 기본 강조, `approved` 상태 아닌 이슈는 발송 라우트가 거절.
- [ ] 이 단계는 플랜의 Iteration 8 을 **마크다운 파일 검수 → 웹 검수** 로 대체합니다. 기존 Iteration 8 항목은 폐기/재작성 필요.

### 우선순위 2 — 백엔드 잔여 이터레이션

원래 플랜 순서대로라면:

- [ ] **Iteration 6** — Practical(일반 임직원) 인사이트 작성기.
  - `prompts/practical-insight/practical-{usecase-generator,prompt-example-generator,risk-checker,insight-writer}.md`
  - `slices/newsletter/practical.py`
- [ ] **Iteration 7** — 통합 뉴스레터 초안.
  - `models/newsletter_issue.py` + 마이그레이션
  - `slices/newsletter/assembler.py`, `slices/newsletter/cli.py` (`draft`)
  - `templates/newsletter.{md,html}.j2`
- [ ] **Iteration 8** — 검수(웹 UI로 재정의 — 우선순위 1과 결합).
- [ ] **Iteration 9** — SMTP 발송. `approved` 게이트 엄격 검증.
- [ ] **Iteration 10** — 모니터링(RunLog, stats, run --until).

### 결정해야 할 것

- Iteration 6 을 먼저 끝낼지(백엔드 완결 후 UI), 아니면 UI 를 우선해 Dashboard 부터 띄울지. 마스터 선택 사항입니다. UI 우선이 동기 부여 측면에서 유리할 것 같고, 그 사이 Practical 트랙은 자투리 시간에 끼워넣어도 무방합니다.

---

## 주요 파일 경로

| 종류 | 경로 |
|------|------|
| 스펙 | `plan/ai_newsletter_service_plan.md` |
| 승인 플랜 | `C:\Users\user\.claude\plans\wondrous-cooking-quill.md` |
| Claude 가이드 | `CLAUDE.md` (프로젝트), `C:\Users\user\.claude\CLAUDE.md` (글로벌) |
| 공통 에이전트 가이드 | `AGENTS.md` |
| 디자인 파일 | `design/newsletter_admin.pen` |
| 핸드오프 노트 | `hitl/260515-iteration-4-5-완료-검수UI-디자인.md` (본 문서) |

---

## 세션 끝 시점 상태

- Git: `main` 브랜치, working tree clean, 마지막 커밋 `c178c65`.
- 테스트: 225/225 통과.
- 린트: 통과.
- 미커밋: 본 문서(`hitl/260515-...md`) 하나만 신규 — 다음 세션 시작 시 추가/커밋 결정.

수고하셨습니다. 다음 세션에서 이어서 가겠습니다.
