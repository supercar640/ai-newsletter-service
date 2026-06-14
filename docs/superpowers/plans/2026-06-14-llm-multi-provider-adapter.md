# LLM 멀티 프로바이더 어댑터 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (인라인 실행).
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** `LLMClient`를 프로바이더 어댑터 위에 재배선해 `.env`의 `LLM_PROVIDER`로 Anthropic ↔ Gemini를 전환할 수 있게 한다.

**Architecture:** `core/llm.py`(단일 파일)를 `core/llm/` 패키지로 확장. `LLMClient`는 프로바이더 독립이고, 어느 모델을 쓸지는 `tier`(fast/quality) + 현재 프로바이더로 해석한다. 어댑터(AnthropicProvider/GeminiProvider)가 각자 SDK 호출과 토큰 추출을 책임진다.

**Tech Stack:** Python 3.12, anthropic SDK, google-genai SDK, pydantic-settings, pytest.

**회귀 기준:** 매 커밋 `uv run pytest -q` 646 passed 유지(커밋 4 이후 신규 테스트만큼 증가).

---

## 파일 구조

```
core/llm/
├── __init__.py    # 공개 재노출: LLMClient, LLMResponse, LLMError, FAST, QUALITY
├── models.py      # FAST/QUALITY 상수, MODELS 매핑, resolve_model(provider, tier)
├── providers.py   # RawCompletion, Provider(Protocol), AnthropicProvider, GeminiProvider, make_provider(settings)
└── client.py      # LLMClient, LLMResponse, LLMError, _first_json_value, _extract helpers
```

기존 `core/llm.py`는 삭제하고 위 패키지로 대체한다. import 경로(`from newsletter.core.llm import LLMClient, LLMResponse, LLMError`)는 `__init__.py` 재노출로 그대로 유지된다.

---

## Task 1: tier → 모델 매핑 (`core/llm/models.py`)

**Files:**
- Move: `src/newsletter/core/llm.py` → `src/newsletter/core/llm/__init__.py` (패키지화, 내용 100% 보존)
- Create: `src/newsletter/core/llm/models.py`
- Test: `tests/test_llm_models.py`

> **Step 0 (충돌 회피):** `git mv src/newsletter/core/llm.py src/newsletter/core/llm/__init__.py`.
> 모듈과 동명 패키지는 공존 불가하므로, 먼저 기존 파일을 그대로 패키지의 `__init__.py`로
> 옮긴다. 내용 변경 없음 → 기존 import·테스트 그대로 green. 이후 단계에서 모듈을 분리한다.

- [ ] **Step 1: 실패 테스트**

```python
# tests/test_llm_models.py
import pytest
from newsletter.core.llm.models import FAST, QUALITY, MODELS, resolve_model

def test_resolve_anthropic():
    assert resolve_model("anthropic", FAST) == "claude-sonnet-4-6"
    assert resolve_model("anthropic", QUALITY) == "claude-opus-4-7"

def test_resolve_gemini():
    assert resolve_model("gemini", FAST) == "gemini-2.5-flash"
    assert resolve_model("gemini", QUALITY) == "gemini-2.5-pro"

def test_resolve_unknown_provider_raises():
    with pytest.raises(KeyError):
        resolve_model("nope", FAST)

def test_resolve_unknown_tier_raises():
    with pytest.raises(KeyError):
        resolve_model("anthropic", "turbo")
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_llm_models.py -q` → ImportError.

- [ ] **Step 3: 구현**

```python
# src/newsletter/core/llm/models.py
"""Tier → concrete model-id resolution, per provider."""
from __future__ import annotations

FAST = "fast"
QUALITY = "quality"

MODELS: dict[str, dict[str, str]] = {
    "anthropic": {FAST: "claude-sonnet-4-6", QUALITY: "claude-opus-4-7"},
    "gemini": {FAST: "gemini-2.5-flash", QUALITY: "gemini-2.5-pro"},
}


def resolve_model(provider: str, tier: str) -> str:
    """Map (provider, tier) to the concrete model id. Raises KeyError if unknown."""
    return MODELS[provider][tier]


__all__ = ["FAST", "QUALITY", "MODELS", "resolve_model"]
```

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_llm_models.py -q` → PASS.
- [ ] **Step 5: 커밋** — `feat(llm): tier→model 매핑 테이블`

---

## Task 2: 프로바이더 어댑터 — Anthropic (`core/llm/providers.py`)

**Files:**
- Create: `src/newsletter/core/llm/providers.py`
- Test: `tests/test_llm_providers.py`

`RawCompletion`, `Provider` 프로토콜, `AnthropicProvider`를 만든다. AnthropicProvider는 기존 `llm.py`의 `messages.create` 호출 + `_extract_text` + usage 추출을 그대로 옮긴다. (GeminiProvider는 Task 5.)

- [ ] **Step 1: 실패 테스트** — 가짜 Anthropic SDK로 요청 구성과 토큰 추출 검증.

```python
# tests/test_llm_providers.py
from dataclasses import dataclass
from newsletter.core.llm.providers import AnthropicProvider, RawCompletion

@dataclass
class _Usage:
    input_tokens: int
    output_tokens: int

@dataclass
class _Block:
    text: str

@dataclass
class _Msg:
    content: list
    usage: _Usage

class _Messages:
    def __init__(self): self.captured = {}
    def create(self, **kw):
        self.captured = kw
        return _Msg(content=[_Block("hi")], usage=_Usage(3, 7))

class _Anthropic:
    def __init__(self): self.messages = _Messages()

def test_anthropic_generate_extracts_text_and_tokens():
    sdk = _Anthropic()
    p = AnthropicProvider(client=sdk)
    out = p.generate("body", model="claude-sonnet-4-6", max_tokens=100, system="sys", temperature=0.2)
    assert isinstance(out, RawCompletion)
    assert out.text == "hi"
    assert (out.input_tokens, out.output_tokens) == (3, 7)
    assert sdk.messages.captured["model"] == "claude-sonnet-4-6"
    assert sdk.messages.captured["system"] == "sys"
    assert sdk.messages.captured["messages"] == [{"role": "user", "content": "body"}]

def test_anthropic_name():
    assert AnthropicProvider(client=_Anthropic()).name == "anthropic"
```

- [ ] **Step 2: 실패 확인**.

- [ ] **Step 3: 구현**

```python
# src/newsletter/core/llm/providers.py
"""Provider adapters: each wraps one vendor SDK behind a uniform interface."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class RawCompletion:
    text: str
    input_tokens: int
    output_tokens: int


@runtime_checkable
class Provider(Protocol):
    name: str
    def generate(
        self, body: str, *, model: str, max_tokens: int,
        system: str | None, temperature: float,
    ) -> RawCompletion: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, *, client: Any | None = None, api_key: str = "") -> None:
        if client is not None:
            self._client = client
        else:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=api_key or "missing")

    def generate(self, body, *, model, max_tokens, system, temperature) -> RawCompletion:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": body}],
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system
        response = self._client.messages.create(**kwargs)
        text = _anthropic_text(response)
        usage = getattr(response, "usage", None)
        return RawCompletion(
            text=text,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        )


def _anthropic_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if not content:
        return ""
    parts = [t for b in content if (t := getattr(b, "text", None))]
    return "".join(parts)


def make_provider(settings) -> Provider:
    """Build the provider named by settings.llm_provider. (Gemini added in Task 5.)"""
    name = settings.llm_provider
    if name == "anthropic":
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    raise ValueError(f"unknown LLM_PROVIDER: {name!r}")


__all__ = ["RawCompletion", "Provider", "AnthropicProvider", "make_provider"]
```

> 참고: `make_provider`는 `settings.llm_provider` / `settings.gemini_api_key`를 읽지만, 이 설정 필드는 Task 4에서 추가된다. 이 태스크 테스트는 `AnthropicProvider`를 직접 생성하므로 settings에 의존하지 않는다.

- [ ] **Step 4: 통과 확인**.
- [ ] **Step 5: 커밋** — `feat(llm): AnthropicProvider 어댑터 + RawCompletion`

---

## Task 3: LLMClient를 tier+provider 기반으로 재배선 (core 전환)

이 태스크는 강결합이라 한 커밋으로 묶는다: `client.py` 신설 + `__init__.py` 재노출 + 기존 `llm.py` 삭제 + `prompts.py`(model→tier) + 9개 프롬프트 frontmatter + 슬라이스 7곳 + 관련 테스트 더블 갱신. 끝에서 전체 646 통과를 회귀 기준으로 확인한다.

**Files:**
- Create: `src/newsletter/core/llm/client.py`, 최종 `src/newsletter/core/llm/__init__.py`
- Delete: `src/newsletter/core/llm.py`
- Modify: `src/newsletter/core/prompts.py` (`Prompt.model` → `Prompt.tier`, frontmatter `tier:` 파싱, required 키 `model`→`tier`)
- Modify: 프롬프트 9개 (`prompts/**/*.md`) frontmatter `model: claude-...` → `tier: fast|quality`
- Modify: 슬라이스 7곳 (아래 목록) `model=prompt.model` → `tier=prompt.tier`
- Modify: 테스트 더블/단언 (아래 목록)

**프롬프트 9개 매핑 (sonnet→fast, opus→quality):**
- fast: `common/keyword-relevance-classifier.md`, `common/track-classifier.md`, `expert-news/expert-importance-scorer.md`, `expert-news/expert-cluster-summarizer.md`, `practical-insight/practical-usecase-summarizer.md`, `practical-insight/practical-department-tips.md`
- quality: `expert-news/expert-news-writer.md`, `practical-insight/practical-insight-writer.md`, `monthly/digest-narrative.md`

**슬라이스 7곳 (`model=prompt.model` → `tier=prompt.tier`):**
`processing/relevance.py:106`, `processing/track_classifier.py:50`, `integration/scoring.py:288`, `newsletter/expert.py:91,166`, `newsletter/practical.py:72,137`, `newsletter/department_tips.py:63`, `monthly/narrative.py:31`

- [ ] **Step 1: `client.py` 작성** — 기존 `llm.py`의 `LLMResponse`/`LLMError`/`complete`/`complete_json`/`complete_prompt`/`_first_json_value`를 옮기되, `model:` 파라미터를 `tier: str = FAST`로 바꾸고 provider를 통해 호출한다.

```python
# src/newsletter/core/llm/client.py
from __future__ import annotations
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from newsletter.core.config import get_settings
from newsletter.core.logging import get_logger
from newsletter.core.prompts import Prompt
from newsletter.core.llm.models import FAST, resolve_model
from newsletter.core.llm.providers import Provider, make_provider

log = get_logger(__name__)


class LLMError(Exception): ...


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


UsageCallback = Callable[["LLMResponse"], None]


class LLMClient:
    def __init__(self, *, provider: Provider | None = None,
                 usage_callback: UsageCallback | None = None) -> None:
        self._provider = provider if provider is not None else make_provider(get_settings())
        self._usage_callback = usage_callback

    def complete(self, body: str, *, tier: str = FAST, max_tokens: int = 1024,
                 system: str | None = None, temperature: float = 0.2) -> LLMResponse:
        model = resolve_model(self._provider.name, tier)
        try:
            raw = self._provider.generate(
                body, model=model, max_tokens=max_tokens,
                system=system, temperature=temperature,
            )
        except Exception as exc:
            raise LLMError(f"{self._provider.name} call failed: {exc}") from exc
        log.info("llm.complete", model=model,
                 input_tokens=raw.input_tokens, output_tokens=raw.output_tokens)
        result = LLMResponse(text=raw.text, model=model,
                             input_tokens=raw.input_tokens, output_tokens=raw.output_tokens)
        if self._usage_callback is not None:
            try:
                self._usage_callback(result)
            except Exception:
                log.exception("llm.usage_callback_failed", model=model)
        return result

    def complete_prompt(self, prompt: Prompt, values: dict[str, Any], *,
                        max_tokens: int = 1024, system: str | None = None,
                        temperature: float = 0.2) -> LLMResponse:
        return self.complete(prompt.render(**values), tier=prompt.tier,
                             max_tokens=max_tokens, system=system, temperature=temperature)

    def complete_json(self, body: str, *, tier: str = FAST, max_tokens: int = 1024,
                      system: str | None = None, temperature: float = 0.0,
                      ) -> tuple[Any, LLMResponse]:
        response = self.complete(body, tier=tier, max_tokens=max_tokens,
                                 system=system, temperature=temperature)
        payload = _first_json_value(response.text)
        if payload is None:
            raise LLMError(f"LLM did not return parseable JSON. Raw: {response.text[:200]!r}")
        return payload, response


def _first_json_value(text: str) -> Any:
    # (기존 llm.py의 _first_json_value 본문을 그대로 이전)
    ...
```

> `_first_json_value`는 기존 `llm.py`에서 글자 그대로 복사한다(로직 변경 없음).

- [ ] **Step 2: `__init__.py` 재노출**

```python
# src/newsletter/core/llm/__init__.py
from newsletter.core.llm.client import LLMClient, LLMResponse, LLMError, _first_json_value
from newsletter.core.llm.models import FAST, QUALITY
__all__ = ["LLMClient", "LLMResponse", "LLMError", "FAST", "QUALITY", "_first_json_value"]
```

- [ ] **Step 3: 기존 `src/newsletter/core/llm.py` 삭제.**

- [ ] **Step 4: `prompts.py` — `model` → `tier`.** `Prompt` 데이터클래스 필드 `model: str` → `tier: str`; `_parse_prompt`의 `required = ("name", "model", "version")` → `("name", "tier", "version")`; `Prompt(... model=str(meta["model"]) ...)` → `tier=str(meta["tier"])`. 검증: tier 값이 `{"fast","quality"}`가 아니면 `PromptError`.

- [ ] **Step 5: 프롬프트 9개 frontmatter 치환** (위 매핑표대로 `model:` 줄 → `tier:` 줄).

- [ ] **Step 6: 슬라이스 7곳 치환** — 각 호출의 `model=prompt.model` → `tier=prompt.tier`.

- [ ] **Step 7: 테스트 더블/단언 갱신**

  - `tests/test_llm.py`: `_FakeAnthropic` 주입을 `FakeProvider`(아래)로 교체, `complete(model=...)` 호출 제거, `prompt=Prompt(... model=...)` → `tier="fast"`. 어댑터 자체 검증은 Task 2의 `test_llm_providers.py`로 이미 커버되므로, 여기선 client의 tier 해석/JSON 파싱/usage 콜백만 본다.

    ```python
    class FakeProvider:
        name = "anthropic"
        def __init__(self, text="", error=None): self.text, self.error = text, error
        def generate(self, body, *, model, max_tokens, system, temperature):
            if self.error: raise self.error
            return RawCompletion(text=self.text, input_tokens=5, output_tokens=10)
    ```
  - `tests/test_prompts.py:21` `assert prompt.model.startswith("claude-")` → `assert prompt.tier in {"fast", "quality"}`.
  - `tests/slices/monitoring/test_recorder.py`: `LLMClient(client=_FakeAnthropic())` → `LLMClient(provider=FakeProvider())`; `client.complete("hi", model="claude-sonnet-4-6")` → `client.complete("hi", tier="fast")`; 기록 model 단언은 `"claude-sonnet-4-6"` 유지(provider.name=anthropic + fast로 해석되므로).
  - 슬라이스 stub들(`tests/slices/newsletter/test_expert.py` `_StubLLM`, `test_practical.py`, `test_narrative.py` `_FakeLLM`, `tests/slices/processing/test_relevance.py`, `test_track_classifier.py`, `tests/slices/integration/test_scoring.py`, `test_department_tips.py`): stub의 `complete`/`complete_json`/`complete_prompt` 시그니처 `model=None` → `tier=None`, 호출 기록 튜플의 `model` → `tier`, `complete_prompt` 내부 `model=prompt.model` → `tier=prompt.tier`로 치환.

- [ ] **Step 8: 전체 회귀** — `uv run pytest -q` → 646 passed.
- [ ] **Step 9: 커밋** — `refactor(llm): tier 기반 LLMClient + 프로바이더 어댑터로 전환`

---

## Task 4: 설정 — provider 선택 + Gemini 키 (`core/config.py`)

**Files:**
- Modify: `src/newsletter/core/config.py`
- Test: `tests/test_config_llm.py`

- [ ] **Step 1: 실패 테스트**

```python
# tests/test_config_llm.py
from newsletter.core.config import Settings

def test_defaults_to_gemini():
    assert Settings().llm_provider == "gemini"

def test_provider_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert Settings().llm_provider == "anthropic"

def test_gemini_key_field(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-123")
    assert Settings().gemini_api_key == "g-123"
```

- [ ] **Step 2: 실패 확인.**
- [ ] **Step 3: 구현** — `config.py`의 Anthropic 블록 근처에 추가:

```python
    # LLM provider selection
    llm_provider: Literal["anthropic", "gemini"] = Field(default="gemini")
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
```

- [ ] **Step 4: 통과 확인.** 그리고 `tests/conftest.py`의 `_EXTERNAL_CREDENTIAL_VARS`에 `"GEMINI_API_KEY"` 추가(테스트가 실제 키를 줍지 않도록), `monkeypatch.setenv("LLM_PROVIDER", "anthropic")`를 `settings` 픽스처에 추가(기본 gemini이지만 테스트 더블은 provider.name=anthropic 가정이므로 명시 고정).
- [ ] **Step 5: 전체 회귀** `uv run pytest -q`.
- [ ] **Step 6: 커밋** — `feat(config): LLM_PROVIDER + GEMINI_API_KEY 설정`

---

## Task 5: GeminiProvider + google-genai 의존성

**Files:**
- Modify: `pyproject.toml` (dependencies에 `google-genai`)
- Modify: `src/newsletter/core/llm/providers.py` (GeminiProvider + make_provider 분기)
- Test: `tests/test_llm_providers.py` (Gemini 케이스 추가)

- [ ] **Step 1: 의존성 추가** — `uv add google-genai && uv sync`. import 형태와 `gemini-2.5-flash`/`gemini-2.5-pro` 모델 ID 호출 가능 여부를 `uv run python -c "from google import genai; from google.genai import types; print('ok')"`로 확인. (모델 ID가 다르면 `models.py`의 `MODELS["gemini"]`만 수정.)

- [ ] **Step 2: 실패 테스트** — 가짜 genai 클라이언트로 요청 구성/토큰 추출 검증.

```python
def test_gemini_generate_extracts_text_and_tokens():
    captured = {}
    class _Models:
        def generate_content(self, **kw):
            captured.update(kw)
            class _U: prompt_token_count = 4; candidates_token_count = 9
            class _R: text = "hello"; usage_metadata = _U()
            return _R()
    class _Client:
        def __init__(self): self.models = _Models()
    from newsletter.core.llm.providers import GeminiProvider, RawCompletion
    p = GeminiProvider(client=_Client())
    out = p.generate("body", model="gemini-2.5-flash", max_tokens=50, system="sys", temperature=0.3)
    assert out == RawCompletion(text="hello", input_tokens=4, output_tokens=9)
    assert captured["model"] == "gemini-2.5-flash"
    assert captured["contents"] == "body"
    assert p.name == "gemini"
```

- [ ] **Step 3: 구현** — `providers.py`에 추가:

```python
class GeminiProvider:
    name = "gemini"

    def __init__(self, *, client: Any | None = None, api_key: str = "") -> None:
        if client is not None:
            self._client = client
        else:
            from google import genai
            self._client = genai.Client(api_key=api_key or "missing")

    def generate(self, body, *, model, max_tokens, system, temperature) -> RawCompletion:
        from google.genai import types
        config = types.GenerateContentConfig(
            system_instruction=system or None,
            max_output_tokens=max_tokens,
            temperature=temperature,
        )
        resp = self._client.models.generate_content(
            model=model, contents=body, config=config,
        )
        usage = getattr(resp, "usage_metadata", None)
        return RawCompletion(
            text=getattr(resp, "text", "") or "",
            input_tokens=int(getattr(usage, "prompt_token_count", 0) or 0),
            output_tokens=int(getattr(usage, "candidates_token_count", 0) or 0),
        )
```

  그리고 `make_provider`에 분기 추가:
```python
    if name == "gemini":
        return GeminiProvider(api_key=settings.gemini_api_key)
```
  `__all__`에 `GeminiProvider` 추가.

- [ ] **Step 4: 통과 확인** + 전체 회귀.
- [ ] **Step 5: 커밋** — `feat(llm): GeminiProvider + google-genai 의존성`

---

## Task 6: 비용 단가 + 문서

**Files:**
- Modify: `src/newsletter/slices/monitoring/pricing.py`
- Modify: `.env.example`, `AGENTS.md`, `CLAUDE.md` 관련 LLM 문구
- Test: `tests/slices/monitoring/test_pricing.py` (있으면 보강, 없으면 신설)

- [ ] **Step 1: Gemini 공식 단가 확인** (Google AI 가격 페이지) 후 `PRICING`에 추가:

```python
    "gemini-2.5-flash": (<in>, <out>),
    "gemini-2.5-pro": (<in>, <out>),
```
  (`<in>/<out>`은 확인한 USD per 1M 값. 근사치 금지 — 확인 후 입력.)

- [ ] **Step 2: 단가 테스트** — `cost_for("gemini-2.5-flash", 1_000_000, 1_000_000)`이 입력한 단가 합과 일치.

- [ ] **Step 3: `.env.example` 갱신** — 상단 Anthropic 블록을 다음으로 교체/보강:

```bash
# === LLM Provider ===
# anthropic | gemini
LLM_PROVIDER=gemini
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
```

- [ ] **Step 4: `AGENTS.md` / `CLAUDE.md`** — LLM 규칙의 "Anthropic SDK 직접 import 금지 / claude-sonnet-4-6·claude-opus-4-7" 문구를 "프로바이더는 `core/llm` 어댑터로만, tier(fast/quality)로 지정, 프로바이더는 `LLM_PROVIDER`로 선택"으로 갱신. 모델 표(Stack)도 멀티 프로바이더로.

- [ ] **Step 5: 전체 회귀** `uv run pytest -q`.
- [ ] **Step 6: 커밋** — `feat(llm): Gemini 단가 + 멀티 프로바이더 문서 갱신`

---

## 마무리

- [ ] 전체 `uv run pytest -q` 그린, `uv run ruff check` 클린.
- [ ] `git push` (단독 레포 → main).
- [ ] 실제 동작은 `.env`에 `LLM_PROVIDER=gemini` + `GEMINI_API_KEY` 채워 한 번 dry 호출로 확인(별도, 마스터 키 필요).

## 미해결 / 구현 시 확인
- `gemini-2.5-flash`/`gemini-2.5-pro` 정확한 모델 ID (Task 5 Step 1에서 검증).
- Gemini 공식 토큰 단가 (Task 6 Step 1에서 확인).
