# CLAUDE.md

> Claude Code 전용 가이드. 다른 에이전트와 공유되는 공통 표준은 [`AGENTS.md`](AGENTS.md)를 따른다.
> 이 파일은 Claude Code에 특화된 톤·응답·작업 규칙만 추가한다.

---

## 호칭·말투

- 사용자는 **"마스터"**라고 부른다.
- 모든 응답은 **존댓말**(`~합니다`, `~해주세요`). 반말 어미 금지.
- 적당한 존대를 유지한다. 극존칭(`마스터님께서…`) 금지.
- 매 문장마다 호칭을 박지 않는다. 어색하면 생략한다.

---

## 프로젝트 한 줄

사내 AI 인텔리전스 뉴스레터 자동화 시스템. AI 뉴스/RSS/유튜브를 수집하고 두 트랙(전문가용 / 일반 임직원용)으로 분류·요약·작성한 뒤, 관리자 검수를 거쳐 이메일로 발송합니다.

---

## 진실 공급원 (충돌 시 우선순위)

1. 마스터의 직접 지시
2. 스펙: [`plan/ai_newsletter_service_plan.md`](plan/ai_newsletter_service_plan.md)
3. 승인된 구현 플랜: `C:\Users\user\.claude\plans\wondrous-cooking-quill.md`
4. [`AGENTS.md`](AGENTS.md) (공통 표준)

`AGENTS.md`와 중복되는 내용은 이 파일에 적지 않습니다. Claude 전용 항목만 다룹니다.

---

## 작업 흐름

- **TDD**: 실패하는 테스트 먼저 → 최소 구현 → 통과 확인 → 커밋.
- **잦은 커밋**: 한 슬라이스 / 한 책임 단위.
- **YAGNI**: 스펙 밖 기능은 만들지 않는다. 추상화는 두 번째 사용처가 생긴 뒤에.
- **확인 후 진행**: 파일 삭제, force push, 외부 API 호출, 실제 이메일 발송 같은 비가역 동작은 마스터 확인을 받습니다. 마스터가 미리 위임한 범위는 예외.
- **상태 머신 가드**: `approved` 검증 없는 발송 코드는 절대 추가하지 않습니다.

---

## 응답 스타일

- 도구 호출 전후로 한 문장씩 짧은 진행 상황만 둡니다. 내적 사고 중계 금지.
- 코드 변경 후에는 "무엇을 했고 다음에 무엇을 할 것인지" 한두 줄로 정리합니다.
- 파일/라인 참조는 `src/newsletter/slices/sources/repository.py:42` 형식.
- 코드는 자체 설명. 주석은 *왜*가 비자명할 때만.

---

## 자주 쓰는 명령 (Claude Code 워크플로 추가)

기본 명령은 `AGENTS.md`의 Setup / Run / Test 참고.

- 의존성 추가: `uv add <pkg>` → `uv sync`
- 마이그레이션 자동 생성: `uv run alembic revision --autogenerate -m "..."`
- 한 슬라이스만 테스트: `uv run pytest tests/slices/sources -v`
- 빠른 정리: `uv run ruff check --fix && uv run ruff format`

---

## LLM·프롬프트 운영 (요약)

상세는 `AGENTS.md`. Claude Code 작업 중 자주 어기기 쉬운 부분:

- `core/llm.py`를 우회하는 직접 `import anthropic` 금지.
- 새 프롬프트는 `prompts/` 하위에 두고 frontmatter(`name, model, version, inputs, output_schema`)를 채웁니다.
- 처리(필터/요약/스코어)는 `claude-sonnet-4-6`, 최종 뉴스레터 작성·편집은 `claude-opus-4-7`.
- 입력은 `title + raw_summary` 우선. 본문 전체 전송 금지.

---

## 절대 금지

- 마스터 확인 없는 자동 발송 코드 추가.
- `.env` 또는 비밀 키 커밋.
- 슬라이스 간 내부 모듈 직접 import (`from newsletter.slices.X._internal import …`).
- 테스트에서 실제 외부 API 호출.
- `git commit --no-verify` (마스터가 명시 요청한 경우 제외).
- 커밋을 amend 해서 이미 푸시된 히스토리 다시 쓰기.

---

## 메모리 활용

- 호칭/말투/현재 날짜 등은 사용자 글로벌 `C:\Users\user\.claude\CLAUDE.md`에서 자동 적용됩니다. 이 파일은 그 위에 프로젝트 특화 규칙만 더합니다.
- 프로젝트 진행 중 알게 된 비자명한 의사결정·운영 메모는 적절히 메모리에 저장합니다.
- 코드에서 유추 가능한 사실(파일 구조, 함수 시그니처 등)은 저장하지 않습니다.

---

## 참고

- 스펙: `plan/ai_newsletter_service_plan.md`
- 공통 에이전트 가이드: `AGENTS.md`
- 승인 플랜: `C:\Users\user\.claude\plans\wondrous-cooking-quill.md`
