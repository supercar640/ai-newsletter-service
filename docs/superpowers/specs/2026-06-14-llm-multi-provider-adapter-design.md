# LLM 멀티 프로바이더 어댑터 — 설계

> 작성일 2026-06-14 · 상태: 승인됨 → 구현 대기

## 배경 / 문제

모든 LLM 호출은 `core/llm.py` 한 곳을 지나지만, 그 파일이 Anthropic SDK
(`from anthropic import Anthropic`, `client.messages.create`)에 직접 묶여 있다.
설정도 `anthropic_api_key` 하나만 읽는다. 따라서 `.env`의 키만 Gemini로 바꿔도
프로바이더가 바뀌지 않고, LLM을 쓰는 모든 단계(관련도 필터·트랙 분류·중요도
스코어링·클러스터 요약·뉴스레터 작성·월간 서술·부서별 팁)가 인증 실패로 깨진다.

## 목표

`LLMClient`의 공개 메서드 집합(`complete`/`complete_json`/`complete_prompt`)을
유지한 채, 내부의 "Anthropic 직접 호출"을 **프로바이더 어댑터**로 추출한다.
`.env`의 `LLM_PROVIDER`로 Anthropic ↔ Gemini를 한 줄로 전환한다.

> 단, 모델 지정 인자는 구체 모델 문자열에서 tier로 바뀐다. 슬라이스가 LLM을
> 부르는 7곳이 `model=prompt.model` → `tier=prompt.tier`로 **기계적으로** 치환된다
> (호출 구조·로직은 그대로). 슬라이스가 프로바이더나 모델 ID를 알 필요는 여전히 없다.

## 비목표 (YAGNI)

- 스트리밍 / 멀티턴 / tool use — 현재 처리 작업에 불필요, 추가 안 함.
- 3번째 프로바이더(OpenAI 등) — 인터페이스는 열어두되 지금 구현하지 않음.
- 런타임 프로바이더 폴백/재시도 체인 — 단일 프로바이더를 명시적으로 선택.

## 결정 사항 (확정)

| 항목 | 결정 |
|---|---|
| 모델 매핑 | 처리(fast)=`gemini-2.5-flash`, 작성(quality)=`gemini-2.5-pro` |
| 프로바이더 선택 | `.env`의 `LLM_PROVIDER=gemini\|anthropic`, 기본값 `gemini` |
| 프롬프트 model 필드 | `model: claude-...` → `tier: fast\|quality` (프로바이더 독립) |

## 아키텍처

`core/llm.py`(단일 파일) → `core/llm/`(패키지)로 확장.

```
core/llm/
├── __init__.py    # 공개 API 재노출 (LLMClient, LLMResponse, LLMError, FAST, QUALITY)
├── client.py      # LLMClient — 프로바이더 독립. complete / complete_json / complete_prompt
├── providers.py   # Provider 프로토콜 + AnthropicProvider + GeminiProvider + RawCompletion
└── models.py      # tier+provider → 실제 모델 ID 매핑, tier 상수, 프로바이더 팩토리
```

공개 인터페이스(`complete` / `complete_json` / `complete_prompt` / `LLMResponse`)는
시그니처와 동작을 그대로 유지한다. 단, 모델 지정 인자가 구체 모델 문자열에서
tier로 바뀐다(`model=MODEL_SONNET` → `tier=FAST`).

### Provider 인터페이스

```python
@dataclass
class RawCompletion:
    text: str
    input_tokens: int
    output_tokens: int

class Provider(Protocol):
    name: str  # "anthropic" | "gemini"
    def generate(
        self, body: str, *, model: str, max_tokens: int,
        system: str | None, temperature: float,
    ) -> RawCompletion: ...
```

각 어댑터의 책임은 단 하나: 자기 SDK를 호출하고 응답에서
`(text, input_tokens, output_tokens)`를 뽑아 `RawCompletion`으로 돌려준다.
`LLMClient`는 어느 프로바이더인지 알지 못한다.

- **AnthropicProvider** — 기존 `messages.create` + `_extract_text` + usage 추출 로직을 그대로 이전.
- **GeminiProvider** — `google-genai`(`client.models.generate_content`). `system`은
  `config.system_instruction`으로, 토큰은 `response.usage_metadata`
  (`prompt_token_count` / `candidates_token_count`)에서 추출.

### tier → 모델 매핑 (`models.py`)

```python
FAST, QUALITY = "fast", "quality"

MODELS = {
    "anthropic": {FAST: "claude-sonnet-4-6", QUALITY: "claude-opus-4-7"},
    "gemini":    {FAST: "gemini-2.5-flash",  QUALITY: "gemini-2.5-pro"},
}
```

`LLMClient.complete(..., tier=FAST)` → 현재 프로바이더 + tier로 실제 모델 ID를
해석 → 어댑터 호출 → 그 **실제 모델 ID를 `LLMResponse.model`에 기록**한다.
덕분에 `RunLog`/`pricing` 비용 추적이 실제 사용 모델 기준으로 정확히 남는다.

### 데이터 흐름

```
slice → LLMClient.complete_prompt(prompt, values)
        → tier = prompt.tier (fast | quality)
        → model_id = MODELS[settings.llm_provider][tier]
        → provider.generate(body, model=model_id, ...)
        → RawCompletion → LLMResponse(model=model_id, tokens...)
        → usage_callback → RunLog (tokens, cost via pricing.cost_for(model_id, ...))
```

## 곁가지 변경

| 파일 | 변경 |
|---|---|
| 슬라이스 LLM 호출 7곳 | `model=prompt.model` → `tier=prompt.tier`. 대상: `processing/relevance.py`, `processing/track_classifier.py`, `integration/scoring.py`, `newsletter/expert.py`(2), `newsletter/practical.py`(2), `newsletter/department_tips.py`, `monthly/narrative.py` |
| `core/config.py` | `llm_provider: Literal["anthropic","gemini"] = "gemini"`, `gemini_api_key: str = ""` 추가. `anthropic_api_key` 유지 |
| `core/prompts.py` | `Prompt.model` → `Prompt.tier`. frontmatter에서 `tier:` 파싱 |
| `prompts/**/*.md` (9개) | `model: claude-sonnet-4-6` → `tier: fast`, `model: claude-opus-4-7` → `tier: quality` |
| `monitoring/pricing.py` | `gemini-2.5-flash`, `gemini-2.5-pro` 단가 추가 (구현 시 공식 단가 확인) |
| `pyproject.toml` | `google-genai` 추가, `anthropic` 유지 |
| `.env.example` | `LLM_PROVIDER`, `GEMINI_API_KEY` 항목 추가 |
| `AGENTS.md` / `CLAUDE.md` | LLM 규칙의 "Claude 전용" 문구를 멀티 프로바이더 + tier 기반으로 갱신 |

## 에러 처리

- 어댑터의 SDK 호출 실패 → 기존과 동일하게 `LLMError`로 감싼다.
- 알 수 없는 `LLM_PROVIDER` 값 → 설정 로드 시점에 명확히 실패(Literal 검증).
- 선택된 프로바이더의 API 키가 비어 있으면 → 호출 시점에 SDK가 명확히 실패
  (기존 Anthropic 동작과 동일하게 "loud failure" 유지).

## 테스트 전략

- 기존 LLM 테스트(`tests/test_llm.py`)의 `LLMClient(client=_FakeAnthropic())` 주입을
  `LLMClient(provider=FakeProvider())` 방식으로 전환한다. `FakeProvider`는
  `generate()`만 흉내내는 작은 더블.
- 어댑터별 단위 테스트 신설: AnthropicProvider / GeminiProvider 각각 가짜 SDK
  클라이언트로 요청 구성과 토큰 추출을 검증.
- tier→model 매핑, 프로바이더 팩토리 단위 테스트.
- `Prompt.tier` 파싱 테스트.
- **회귀 기준: 전체 646개 통과를 끝까지 유지.** 공개 동작·결과는 동일해야 한다.
- 테스트는 실제 외부 API를 호출하지 않는다(기존 규칙 유지).

## 구현 순서 (커밋 단위)

1. `core/llm/` 패키지 골격: Provider 프로토콜, `RawCompletion`, tier 매핑, 팩토리.
2. `AnthropicProvider`로 기존 동작 이전 + `LLMClient`를 어댑터 위로 재배선 (646 유지).
3. `GeminiProvider` + `google-genai` 의존성 + 어댑터 단위 테스트.
4. `config`에 `llm_provider` / `gemini_api_key`.
5. `Prompt.model` → `tier` + 9개 프롬프트 파일 frontmatter 갱신.
6. `pricing` Gemini 단가 + `.env.example` + `AGENTS.md`/`CLAUDE.md` 문서 갱신.

## 미해결 / 구현 시 확인

- `gemini-2.5-flash` / `gemini-2.5-pro`가 `google-genai`에서 실제 호출 가능한
  정확한 모델 ID인지 첫 단계에서 검증(다르면 `MODELS` 테이블만 수정).
- Gemini 공식 토큰 단가를 `pricing.py`에 반영(현재 값은 근사치 금지, 확인 후 입력).
