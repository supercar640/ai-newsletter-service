# 260521 핸드오프 — Phase 3 트렌드 분석 (trends 슬라이스) 완료

> Human-in-the-loop 작업 정리 노트. 진실 공급원: `plan/ai_newsletter_service_plan.md`,
> 승인 플랜 `C:\Users\user\.claude\plans\wondrous-cooking-quill.md`.

---

## 한 줄 요약

Phase 3 두 번째 항목 **트렌드 분석**을 브레인스토밍 → 설계 → 플랜 → 서브에이전트 TDD
(태스크별 2단계 리뷰)로 완료했습니다. 새 `trends` 슬라이스가 누적 ProcessedItem 제목
키워드의 기간 간 변화를 결정적 리포트로 보여줍니다. `main` 병합 완료, **전체 테스트
560개 통과**, 워킹 트리 클린.

---

## 이번 세션에서 완료한 작업

### 트렌드 분석 — `trends` 슬라이스 (main 병합 커밋 `cda385f`)

누적 ProcessedItem의 제목 키워드를 두 기간(현재 vs 직전)으로 집계해 떠오르는/식는/
신규/소멸 용어를 기사 수 delta로 보여주는 독립 리포트(CLI + 마크다운). 결정적, LLM·
새 테이블·영속화 없음.

산출물:
- `src/newsletter/core/text.py` — 공유 `tokenize()` + `STOPWORDS`. corpus.chunking에서
  추출(corpus는 이제 이걸 재사용, 동작 보존).
- `src/newsletter/slices/trends/terms.py` — `title_terms(title) -> set[str]`(기사당 중복 제거).
- `trends/schemas.py` — `WindowSpec`, `TermDelta`, `TrendBuckets`, `TrendReport`.
- `trends/analysis.py` — `compare_windows`: new/dropped/rising/fading/top_current 분류,
  min_count 노이즈 필터, top_n 절단, 결정적 정렬(term 최종 타이브레이크).
- `trends/service.py` — `build_window_spec`(week=7일/month=30일 고정, end inclusive),
  `analyze_trends`(ProcessedItem⋈RawItem 조회, `published_at` 앵커·`created_at` 폴백,
  half-open 윈도우 버킷팅, 용어→기사수 집계).
- `trends/report.py` — `render_markdown`(섹션별 표, 빈 섹션 "(없음)").
- `trends/cli.py` — `newsletter trends --period --end --top --min-count --save`.
- `cli.py` 루트 등록, `AGENTS.md` 갱신.
- 설계 문서 `docs/superpowers/specs/2026-05-21-trend-analysis-design.md`,
  구현 플랜 `docs/superpowers/plans/2026-05-21-trend-analysis.md`.

테스트 25개 추가(core/text 4, terms 3, analysis 6, service 6(경계 포함), report 3, cli 3).
전체 535 → 560.

### 검증 상태(세션 종료 시점)

- `uv run pytest` → **560/560 통과** (병합 후 재확인).
- `uv run ruff check`(신규/수정 파일) → 통과.
- `main` 워킹 트리 클린. 피처 브랜치 `feat/trend-analysis` 병합 후 삭제.

---

## 주의/메모 (비자명한 결정)

- **결정적·LLM 없음**: 첫 슬라이스는 기사 수 기반 결정적 집계만. 내러티브 요약·스냅샷
  영속화·의미 클러스터는 비목표(향후 항목).
- **추적 단위 = 제목 키워드**: `keywords`(좁은 관련도 어휘)·`category`(거친 소스값)보다
  제목 토큰화가 신규 엔티티 포착에 풍부.
- **윈도우**: 고정 길이(week 7일/month 30일, 자연월 아님), end inclusive(상한 exclusive
  = end+1일). 현재=[end−Δ+1, end+1), 직전=그 앞 Δ일. half-open·비중첩(경계 테스트로 핀).
- **앵커**: `published_at` 우선, NULL이면 `created_at`(스코어링 recency 철학과 동일).
  SQL 필터와 Python 버킷팅이 동일 naive 값으로 정합(리뷰 검증).
- **min_count vs total UX**: 리포트 헤더 기사 수는 윈도우 전체, 섹션 용어는 min_count
  필터 적용. 모든 용어가 임계 미만이면 헤더는 N건인데 섹션은 "(없음)"일 수 있음(허용).
- **fading 비대칭**: fading은 직전 강도(`previous >= min_count`)로 판정 — 현재 c가
  임계 미만이어도 "식는" 신호로 포함. 의도된 동작.

---

## Phase 진행 상황 (플랜 §25)

- **Phase 1 (MVP)**: 완료.
- **Phase 2 (품질 개선)**: 6개 전부 완료.
- **Phase 3 (고도화)**: 진행 중.
  1. 회사 관심사 RAG — corpus 슬라이스 (완료)
  2. **트렌드 분석** — trends 슬라이스 (이번 세션 완료)
  - [ ] 경쟁사 모니터링 — 특정 기업/제품 추적(소스/스코어링 확장)
  - [ ] 자동 월간 리포트 — 월간 AI 동향 보고서(trends + LLM 내러티브 결합 후보)
  - [ ] 성과 대시보드 — 소스별 성과·클릭률·품질 지표
  - [ ] 부서별 맞춤 뉴스레터 — 독자 그룹별 콘텐츠(스펙 §10 "초기엔 통합본" 재확인 필요)

---

## 다음 세션에 이어서 할 일 (선택)

- Phase 3 남은 항목 중 하나를 마스터가 골라 동일 흐름(브레인스토밍 → 설계 → TDD).
- trends 후속(선택): LLM 내러티브 요약(자동 월간 리포트와 결합), 스냅샷 영속화(대시보드),
  자연월 윈도우, 뉴스레터 §1 "핵심 동향" 섹션 주입.
- 잔여 정리(기존부터): CLI 단일 명령 평탄화, ruff format 전역 통일 PR.

---

## 세션 끝 시점 상태

- Git: `main`, working tree clean, 마지막 커밋 `cda385f`(병합 커밋).
- 테스트: 560/560 통과. 린트: 통과.
- 미커밋: 본 핸드오프 문서 하나만 신규.

수고하셨습니다. 다음 세션에서 Phase 3 다음 항목으로 이어가겠습니다.
