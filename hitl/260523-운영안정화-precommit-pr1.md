# 260523 — 운영 안정화 · pre-commit 도입 (PR #1)

> 어제(2026-05-22)까지 Phase 1~3 + 스펙 밖 항목(리포트 HTML 테마, `site` 정적 사이트)이
> 전부 머지된 상태에서 시작. 오늘은 신규 기능 대신 **운영 안정화·회귀 점검**을 진행.

## 한 일

### 1. 회귀 점검 (baseline 확인)
- 전체 테스트 **646 passed**.
- `uv run alembic check` → "No new upgrade operations" — 모델 ↔ 마이그레이션 drift 없음.

### 2. 코드 위생 drift 정리 + 근본 원인 차단
- `ruff check --fix && ruff format` 일괄 적용 → **40개 파일** 정리(순수 포맷·import 정렬,
  동작 변화 없음, 테스트 646 유지).
- **근본 원인**: pre-commit 훅이 실제로는 없었는데 `CLAUDE.md`는 `--no-verify` 금지를
  명시하며 훅 존재를 전제 → 포맷/정렬 누락이 그대로 커밋에 누적돼 있었음.
- **pre-commit 프레임워크 도입** (`.pre-commit-config.yaml`):
  - ruff lint(`--fix`) / ruff-format
  - trailing-whitespace / end-of-file-fixer / check-yaml / check-toml /
    check-merge-conflict / check-added-large-files
  - dev 의존성에 `pre-commit` 추가, `AGENTS.md` Setup에 `uv run pre-commit install` 안내.
  - 도입 시 EOF 개행 누락 3개 파일 함께 정리.

### 3. 통합
- 브랜치 `chore/lint-format-cleanup` (커밋 2개) → **PR #1 원격 머지** 완료.
  로컬 머지 안 함(아래 규칙).

## 워크플로 규칙 확정 (전역)
- 과거 사고: 로컬 머지만 하고 원격에 안 올린 상태에서 다른 노트북이 GitHub pull로
  작업 → 같은 작업분 중복 → 충돌.
- **결정**: 로컬 머지 금지. 통합은 항상 `push → PR → 원격 머지` 경유. 원격을 단일
  진실 공급원으로 유지. → 전역 `~/.claude/CLAUDE.md`에 "Git 워크플로" 섹션으로 박음.

## 산출물
- 시스템 동작 브리핑 HTML 작성: `hitl/2026-05-23_완성_1차_브리핑.html`.
  생성 산출물이라 커밋 제외 → `.gitignore`에 `hitl/*.html` 추가
  (`.md` 세션 노트는 계속 추적).

## 다음 후보
- 실 운영 리허설: `.env` 키 채우고 `run --no-llm`부터 끝까지 한 사이클 dry 실행.
- 발송 추적(오픈율/클릭률) 인프라 — 이벤트 테이블·링크 래핑·픽셀·웹훅 필요한 별도 큰 작업.
