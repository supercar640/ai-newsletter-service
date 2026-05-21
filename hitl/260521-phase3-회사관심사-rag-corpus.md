# 260521 핸드오프 — Phase 3 첫 항목 완료 (회사 관심사 RAG / corpus 슬라이스)

> Human-in-the-loop 작업 정리 노트. 다음 세션이 끊김 없이 이어갈 수 있도록 합니다.
> 진실 공급원: `plan/ai_newsletter_service_plan.md`, 승인 플랜 `C:\Users\user\.claude\plans\wondrous-cooking-quill.md`.

---

## 한 줄 요약

Phase 3의 첫 항목 **회사 관심사 RAG**를 브레인스토밍 → 설계 문서 → 구현 플랜 →
서브에이전트 기반 TDD(태스크별 2단계 리뷰) 흐름으로 완료했습니다. 새 `corpus`
슬라이스가 사내 문서를 인덱싱해 중요도 스코어링을 보강합니다. `main`에 병합 완료,
**전체 테스트 535개 통과**, 워킹 트리 클린.

---

## 이번 세션에서 완료한 작업

### 회사 관심사 RAG — `corpus` 슬라이스 (main 병합 커밋 `06d0035`)

기존 `interests`(운영자 큐레이션 키워드+임베딩 1개)를 넘어, **사내 문서 디렉터리**를
청크 단위로 인덱싱하고 뉴스 아이템과의 의미적 관련도를 스코어에 추가 배수로 반영.

산출물:
- `src/newsletter/slices/corpus/chunking.py` — 순수 함수. 마크다운 헤딩/문단 단위
  청크 분할(`chunk_text`, max_chars 가드) + 빈도순 키워드 추출(`extract_keywords`).
- `src/newsletter/models/context_chunk.py` — `context_chunks` 테이블. (source_path,
  chunk_index) 유니크. 마이그레이션 `ddc1e6feada8`.
- `src/newsletter/slices/corpus/repository.py` — `ChunkInsert`,
  `replace_file_chunks`(파일 단위 멱등 교체), `file_hashes`(증분 비교), `list_chunks`,
  `delete_all`, `load_keywords`.
- `src/newsletter/slices/corpus/indexer.py` — `index_corpus`: 디렉터리 재귀 스캔 →
  파일 해시 비교 → 변경분만 재청크+배치 임베딩 → 영속화. `IndexReport` 반환.
- `src/newsletter/slices/integration/scoring.py` — `CorpusChunk` +
  `corpus_relevance_factor`([1.0, 1.3], `_CORPUS_CAP=0.3`). `score_items`에
  `corpus_chunks` 인자 추가 → `base × interest_match × corpus_relevance`.
- `src/newsletter/slices/integration/service.py` — `_load_corpus_chunks` 로드 후 전달.
- `src/newsletter/slices/corpus/cli.py` — `newsletter corpus index/list/clear/status`.
- 설정 `COMPANY_CONTEXT_DIR`(빈 값=off), `.env.example` / `AGENTS.md` 갱신.
- 설계 문서 `docs/superpowers/specs/2026-05-21-company-interest-rag-design.md`,
  구현 플랜 `docs/superpowers/plans/2026-05-21-company-interest-rag.md`.

테스트 약 33개 추가(chunking 8 / repository 5 / indexer 7 / scoring 7 / service 2 /
cli 4). 전체 502 → 535.

### 검증 상태(세션 종료 시점)

- `uv run pytest` → **535/535 통과** (병합 후 재확인 완료).
- `uv run ruff check` (신규/수정 파일) → 통과.
- Alembic head = `ddc1e6feada8` (dev DB 적용 완료).
- `main` 워킹 트리 클린. 피처 브랜치 `feat/company-interest-rag` 병합 후 삭제.

---

## 주의/메모 (비자명한 결정)

- **스코어링은 boost-only**: corpus 배수는 [1.0, 1.3]로 감점 없음(기존 interests와
  동일 철학). interests CAP 0.5보다 보수적인 0.3 — 두 보강이 곱해지기 때문.
- **임베딩 우선, 키워드 폴백**: 아이템·청크 모두 임베딩이 있으면 max 코사인 경로,
  아니면 distinct 코퍼스 키워드 겹침(saturation 3). interests는 둘 중 max를 쓰지만
  corpus는 청크가 많아 키워드 합산이 과해지므로 폴백 전용으로 단순화.
- **빈 청크 파일 처리**: 내용이 없는 파일은 행을 만들지 않아 해시 추적이 안 됨 →
  매 실행 재스캔(임베딩 호출은 없으므로 저렴). 인덱서가 indexed로 세지 않고 고아
  청크만 정리. 삭제된 파일 자동 정리는 미구현(YAGNI; `corpus clear` 후 재인덱싱).
- **회귀 0**: `corpus_chunks` None/빈 리스트 → 배수 1.0. `COMPANY_CONTEXT_DIR`
  미설정/청크 0개/임베딩 키 없음 모두 우아하게 degrade. 기존 스코어링·interests·
  작성 프롬프트 무변경.
- **CLI 평탄화**: `corpus`는 다중 명령 Typer라 `newsletter corpus index`로 직접
  호출됨(send/slack의 중첩 quirk 없음). [[cli-subcommand-nesting]] 참고.

---

## Phase 진행 상황

플랜 §25 기준.

- **Phase 1 (MVP)**: 완료.
- **Phase 2 (품질 개선)**: 6개 전부 완료.
- **Phase 3 (고도화)**: 진행 중.
  1. **회사 관심사 RAG** — corpus 슬라이스 (이번 세션 완료)
  - [ ] 트렌드 분석 — 주간/월간 변화 추적(누적 ProcessedItem/이슈 기반)
  - [ ] 경쟁사 모니터링 — 특정 기업/제품 추적(소스/스코어링 확장)
  - [ ] 자동 월간 리포트 — 월간 AI 동향 보고서 자동 생성
  - [ ] 성과 대시보드 — 소스별 성과·클릭률·품질 지표
  - [ ] 부서별 맞춤 뉴스레터 — 독자 그룹별 콘텐츠(스펙 §10 "초기엔 통합본으로
        충분" → 우선순위 재확인 필요)

---

## 다음 세션에 이어서 할 일 (선택)

- Phase 3 남은 항목 중 하나를 마스터가 골라 동일 흐름(브레인스토밍 → 설계 문서 →
  TDD)으로 시작.
- corpus 관련 후속(선택): `corpus status`를 설계 문서의 "신규/변경/삭제 파일
  카운트"까지 확장(현재는 indexed files 수 + 키 유무만 표시); 삭제된 파일 자동 정리.
- 잔여 정리(기존부터): CLI 단일 명령 평탄화, ruff format 전역 통일 PR.

---

## 주요 파일 경로

| 종류 | 경로 |
|------|------|
| 스펙 | `plan/ai_newsletter_service_plan.md` |
| 설계 문서 | `docs/superpowers/specs/2026-05-21-company-interest-rag-design.md` |
| 구현 플랜 | `docs/superpowers/plans/2026-05-21-company-interest-rag.md` |
| 새 슬라이스 | `src/newsletter/slices/corpus/` |
| 공통 에이전트 가이드 | `AGENTS.md` |
| 핸드오프 노트 | `hitl/260521-phase3-회사관심사-rag-corpus.md` (본 문서) |

---

## 세션 끝 시점 상태

- Git: `main` 브랜치, working tree clean, 마지막 커밋 `06d0035`(병합 커밋).
- 테스트: 535/535 통과. 린트: 통과.
- 미커밋: 본 핸드오프 문서 하나만 신규 — 다음 세션 시작 시 추가/커밋 결정.

수고하셨습니다. 다음 세션에서 Phase 3 다음 항목으로 이어가겠습니다.
