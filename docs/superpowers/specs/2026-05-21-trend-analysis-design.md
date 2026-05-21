# 트렌드 분석 — 누적 ProcessedItem 기반 주간/월간 동향 리포트 (Phase 3)

> 설계 문서. 진실 공급원: `plan/ai_newsletter_service_plan.md` §25 Phase 3, 승인 플랜
> `C:\Users\user\.claude\plans\wondrous-cooking-quill.md`. 작성일 2026-05-21.

---

## 한 줄 요약

누적된 `ProcessedItem`의 **제목 키워드**를 두 기간(현재 vs 직전)으로 집계해, 떠오르는/
식는/신규/소멸 용어를 기사 수 변화(delta)로 보여주는 **독립 분석 리포트**(CLI + 마크다운)를
생성합니다. 결정적 집계만 사용하며(LLM 없음), 새 테이블·영속화 없이 누적 데이터에서 매번
재계산합니다.

플랜 §25 "트렌드 분석 — 주간/월간 변화 추적"에 해당합니다.

---

## 목표 / 비목표

**목표**
- 누적 ProcessedItem에서 제목 용어의 시간적 변화를 추적.
- 두 기간 비교로 rising / fading / new / dropped 용어를 기사 수 delta로 제시.
- 주간/월간 고정 길이 윈도우(7일 / 30일) 지원.
- 결정적·재현 가능. 데이터 없으면 우아하게 안내(회귀 0 — 기존 동작 무변경).

**비목표 (YAGNI)**
- LLM 내러티브 요약(결정적 집계만; 향후 자동 월간 리포트 항목과 결합 가능).
- 트렌드 스냅샷 영속화/이력 테이블(별도 대시보드 항목).
- 의미 임베딩 클러스터 테마(장기 고도화).
- 뉴스레터 섹션 주입(이번엔 독립 리포트만).
- 캘린더 월(1일~말일) 정렬 — 비교를 위해 고정 길이 윈도우 사용.

---

## 결정 사항 (브레인스토밍 합의)

1. **1차 소비처**: 독립 분석 리포트(운영자/분석용 CLI + 마크다운).
2. **추적 단위**: 제목 키워드(`normalized_title` 토큰화). 신규 엔티티 포착에 가장 풍부.
3. **비교 방식**: 두 기간 비교(현재 vs 직전) — rising/fading/new/dropped.
4. **랭킹 지표**: 기사 수(용어가 등장한 고유 ProcessedItem 수). 동률은 importance_score 합 보조.
5. **기간 앵커**: `RawItem.published_at` 우선, NULL이면 `ProcessedItem.created_at` 폴백.
6. **토큰화 공유**: `core/text.py`로 추출해 corpus와 trends가 공유(DRY).

---

## 공유 토큰화 — `src/newsletter/core/text.py` (신규)

```python
def tokenize(text: str) -> list[str]:
    """Lowercased word tokens, dropping length-1 tokens and stopwords."""
```

- `_TOKEN_RE = re.compile(r"[0-9a-z가-힣]+")` (소문자화 후 적용).
- `STOPWORDS: frozenset[str]` — corpus.chunking에서 옮겨온 light 불용어 집합(영문 glue +
  한국어 조사/필러).
- 결정적. IO·DB 없음.

**corpus/chunking.py 리팩터 (동작 보존)**
- `extract_keywords`가 `Counter(tokenize(text)).most_common`를 사용하도록 변경:
  ```python
  def extract_keywords(text, *, max_keywords=20):
      counts = Counter(tokenize(text))
      ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
      return [t for t, _ in ranked[:max_keywords]]
  ```
- `chunking.py`의 `_TOKEN_RE` / `_STOPWORDS`는 제거하고 `core.text`에서 import.
- 기존 8개 chunking 테스트가 회귀 가드. (특히 빈도순·불용어 테스트.)

---

## 슬라이스 구조 — `src/newsletter/slices/trends/` (모델·마이그레이션 없음)

```
trends/
  __init__.py
  terms.py      # 순수: title -> set[str]
  analysis.py   # 순수: 두 빈도 맵 비교 -> TrendReport
  service.py    # DB: 두 윈도우 조회 -> 용어 집계 -> compare
  report.py     # 순수: TrendReport -> 마크다운
  schemas.py    # WindowSpec, TermDelta, TrendReport
  cli.py        # newsletter trends
```

### `schemas.py`

```python
@dataclass(frozen=True, slots=True)
class WindowSpec:
    period: str          # "week" | "month"
    current_start: date
    current_end: date    # exclusive
    previous_start: date
    previous_end: date   # exclusive == current_start

@dataclass(frozen=True, slots=True)
class TermDelta:
    term: str
    current: int         # article count this window
    previous: int        # article count prior window
    delta: int           # current - previous
    importance: float    # sum of importance_score this window (tiebreak)

@dataclass(frozen=True, slots=True)
class TrendReport:
    window: WindowSpec
    rising: list[TermDelta]
    fading: list[TermDelta]
    new: list[TermDelta]
    dropped: list[TermDelta]
    top_current: list[TermDelta]   # highest current-window counts overall
    total_current_items: int
    total_previous_items: int
```

### `terms.py` (순수)

```python
def title_terms(title: str) -> set[str]:
    """Distinct terms in a title (per-article dedup)."""
    return set(tokenize(title))
```

### `analysis.py` (순수, DB 없음)

```python
@dataclass(frozen=True, slots=True)
class TrendBuckets:
    rising: list[TermDelta]
    fading: list[TermDelta]
    new: list[TermDelta]
    dropped: list[TermDelta]
    top_current: list[TermDelta]


def compare_windows(
    current: dict[str, int],
    previous: dict[str, int],
    *,
    importance: dict[str, float],
    top_n: int = 15,
    min_count: int = 2,
) -> TrendBuckets:
    """Classify terms into rising/fading/new/dropped/top_current buckets."""
```

- 입력: `current`/`previous` = term → 기사 수, `importance` = term → 현재 윈도우 importance 합.
- 분류 (현재 c, 직전 p):
  - **new**: `p == 0 and c >= min_count`
  - **dropped**: `c == 0 and p >= min_count`
  - **rising**: `c > p > 0 and c >= min_count`
  - **fading**: `0 < c < p and p >= min_count`
  - stable(`c == p`)는 별도 분류하지 않음(top_current에만 반영 가능).
- `min_count` 미만(현재·직전 모두) 용어는 노이즈로 제외. dropped는 `p >= min_count` 기준.
- 정렬: rising/new는 `(delta desc, importance desc, term)`; fading/dropped는 `(delta asc,
  ...)`; top_current는 `(current desc, importance desc, term)`. 각 top_n개로 절단.
- `TrendBuckets`(5개 리스트)를 반환. 서비스가 여기에 `WindowSpec` + `total_*_items`를
  더해 최종 `TrendReport`로 조립.

### `service.py` (DB)

```python
def build_window_spec(period: str, end: date) -> WindowSpec: ...

def analyze_trends(
    session, *, period: str = "week", end: date | None = None,
    top_n: int = 15, min_count: int = 2,
) -> TrendReport: ...
```

- `build_window_spec`: `period`별 Δ(week=7, month=30)로 두 윈도우 계산. `end` 기본 today.
- `analyze_trends`:
  - 두 윈도우 각각, `ProcessedItem ⋈ RawItem` 조회. 앵커 시각 = `coalesce(published_at,
    created_at)`. (SQLite tz 처리는 기존 service 패턴대로 naive→UTC 취급.)
  - 각 아이템: `title_terms(normalized_title)` → 용어별 고유 기사 수 누적(한 기사가 같은
    용어 여러 번 → 1로). 현재 윈도우는 importance 합도 누적.
  - `compare_windows` 호출 → `TrendReport` 반환(`total_*_items` 포함).

### `report.py` (순수)

```python
def render_markdown(report: TrendReport) -> str: ...
```

- 헤더(기간·날짜 범위·기사 수), 섹션: "🔼 떠오르는", "🆕 신규", "🔽 식는", "⬇️ 소멸",
  "📊 현재 상위". 각 표: `term | 현재 | 직전 | Δ`. 빈 섹션은 "(없음)".

### `cli.py` — `newsletter trends`

- `stats`처럼 `invoke_without_command=True` 콜백으로 `newsletter trends` 직접 호출.
- 옵션: `--period [week|month]`(기본 week), `--end YYYY-MM-DD|today`(기본 today),
  `--top INT`(기본 15), `--min-count INT`(기본 2), `--save PATH`(마크다운 파일; 생략 시
  콘솔 출력).
- 빈 윈도우(현재·직전 모두 0 아이템) → "(no items in window)" 안내 후 종료.
- 루트 등록: `app.add_typer(trends_app, name="trends")`.

---

## 기간/윈도우 정의

- 고정 길이 윈도우(비교 동일 길이): week Δ=7일, month Δ=30일.
- `end`(exclusive 상한, 기본 today): 현재=[end−Δ, end), 직전=[end−2Δ, end−Δ).
- 앵커: `published_at` 우선, NULL이면 `created_at`.

---

## 회귀 안전

- 새 슬라이스 + `core/text.py` 추출은 기존 동작 보존(`extract_keywords` 결과 불변, 기존
  corpus 테스트 통과).
- 데이터 없으면 빈 리포트/안내. 기존 스코어링·처리·작성 경로 무변경.

---

## 테스트 계획 (~19 + 회귀)

| 대상 | 개수 | 핵심 케이스 |
|---|---|---|
| `core/text.tokenize` | ~3 | 소문자화, 길이1·불용어 제거, 한/영 토큰 |
| corpus 회귀 | (8) | 기존 chunking 테스트 통과(extract_keywords 불변) |
| `terms.title_terms` | ~2 | 중복 제거, 빈 제목 |
| `analysis.compare_windows` | ~6 | new/dropped/rising/fading 분류, min_count 필터, top_n 절단, 정렬·동률 importance |
| `service.analyze_trends` | ~3 | 두 윈도우 분리, published_at NULL→created_at 폴백, 빈 윈도우 |
| `report.render_markdown` | ~2 | 섹션 포함, 빈 섹션 "(없음)" |
| `cli` | ~3 | week 실행, --save, 빈 윈도우 안내 |

- 서비스 테스트는 `published_at`을 윈도우 경계 양쪽에 두어 분리를 검증. 실제 LLM/외부 호출 없음.

---

## 구현 순서 (슬라이스 단위 커밋)

1. `core/text.py` + 테스트, `corpus/chunking.py` 리팩터(회귀 확인).
2. `trends/terms.py` + 테스트.
3. `trends/schemas.py` + `trends/analysis.py` + 테스트.
4. `trends/service.py` + 테스트.
5. `trends/report.py` + 테스트.
6. `trends/cli.py` + 루트 등록 + 테스트.
7. `AGENTS.md` 갱신.

각 단계: 실패 테스트 → 최소 구현 → 통과 → 커밋.

---

## 주요 파일

| 종류 | 경로 |
|---|---|
| 신규 공유 | `src/newsletter/core/text.py` |
| 리팩터 | `src/newsletter/slices/corpus/chunking.py` |
| 신규 슬라이스 | `src/newsletter/slices/trends/{terms,analysis,service,report,schemas,cli}.py` |
| 수정 | `src/newsletter/cli.py`, `AGENTS.md` |
