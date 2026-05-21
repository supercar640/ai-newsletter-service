# 경쟁사 모니터링 — 경쟁사 멘션 리포트 (Phase 3)

> 설계 문서. 진실 공급원: `plan/ai_newsletter_service_plan.md` §25 Phase 3, 승인 플랜
> `C:\Users\user\.claude\plans\wondrous-cooking-quill.md`. 작성일 2026-05-21.

---

## 한 줄 요약

운영자가 등록한 경쟁사(이름 + 별칭/제품명)를 누적 ProcessedItem의 제목+요약에서 탐지해,
경쟁사별 언급 기사 수 + 대표 헤드라인을 보여주는 **독립 리포트**(CLI + 마크다운)를
생성합니다. 결정적 별칭 매칭만 사용하며(LLM 없음), 단일 룩백 윈도우에서 매번 재계산합니다.

플랜 §25 "경쟁사 모니터링 — 특정 기업/제품 추적"에 해당합니다.

---

## 목표 / 비목표

**목표**
- 경쟁사 레지스트리(이름 + 별칭 목록) CRUD.
- 윈도우 내 수집 기사에서 경쟁사 별칭을 탐지해 경쟁사별로 귀속.
- 경쟁사별 언급 수 + 대표 헤드라인(제목 + 링크, 중요도순) 리포트.
- 데이터/경쟁사 없으면 우아하게 안내(회귀 0 — 기존 동작 무변경).

**비목표 (YAGNI)**
- 스코어링 부스트(이미 `interests`로 가능 — 의미 중복).
- ProcessedItem 영속 태깅(별도 인프라; 리포트는 온디맨드 재계산).
- 임베딩 의미 매칭(경쟁사는 명명 엔티티 → 별칭 매칭).
- 경쟁사 전용 소스 자동 추가(소스 레지스트리로 수동 등록 가능).
- LLM 요약·기간 대비 증감(향후 항목; 자동 월간 리포트와 결합 가능).

---

## 결정 사항 (브레인스토밍 합의)

1. **1차 산출물**: 경쟁사 멘션 리포트(독립 CLI + 마크다운). `interests`(점수 부스트)와 차별.
2. **레지스트리**: 새 `competitors` 테이블(interests/departments 패턴). CompanyInterest 재사용 안 함.
3. **리포트 내용**: 경쟁사별 카운트 + 대표 헤드라인(제목 + 링크).
4. **매칭**: 별칭 기반 결정적 매칭. ASCII 별칭은 단어 경계, 비ASCII(한글 등)는 부분 문자열.
5. **윈도우**: 단일 룩백(`--days` 또는 `--since`). 앵커 `published_at` 우선, NULL이면 `created_at`.

---

## 데이터 모델 — `src/newsletter/models/competitor.py`

`competitors` 테이블. 경쟁사 한 곳 = 한 행.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | int PK | |
| `name` | str(100) | 표시 이름. 유니크(`uq_competitors_name`) |
| `aliases_json` | Text | 별칭/제품명 JSON 배열. 매칭 대상(소문자 비교) |
| `enabled` | bool default True | 비활성 시 탐지 제외 |
| `created_at` | DateTime(tz) | server_default now() |

- 임베딩 없음. 마이그레이션: Alembic autogenerate, `competitors` 신규 테이블.
- 시드 없음(경쟁사는 조직별 — 운영자가 등록).

---

## 슬라이스 구조 — `src/newsletter/slices/competitors/`

```
competitors/
  __init__.py
  matching.py     # 순수: 별칭 매칭
  repository.py   # DB: 레지스트리 CRUD
  schemas.py      # Create/Update/Read + 리포트 dataclass
  service.py      # DB: 윈도우 조회 → 탐지 → CompetitorReport
  report.py       # 순수: CompetitorReport → 마크다운
  cli.py          # newsletter competitors add/list/remove/enable/disable/report
```

### `matching.py` (순수, IO 없음)

```python
def alias_matches(text_lower: str, alias_lower: str) -> bool:
    """True if alias occurs in already-lowercased text.

    ASCII aliases match on word boundaries (so "meta" does not match
    "metadata"); non-ASCII aliases (Korean, etc.) match as substrings
    (Korean particles attach with no boundary, so \\b is unusable).
    """

def mentioned_competitor_ids(
    text_lower: str, competitors: list[CompetitorProfile]
) -> set[int]:
    """Ids of competitors with any alias present in the text."""
```

- `CompetitorProfile`(dataclass): `id: int`, `name: str`, `aliases: tuple[str, ...]`(소문자).
- ASCII 판정: `alias.isascii()`. ASCII면 `re.search(r"\b" + re.escape(alias) + r"\b", text_lower)`,
  아니면 `alias in text_lower`. 빈 별칭은 무시.

### `repository.py` (DB, interests 패턴)

- `add(session, CompetitorCreate) -> Competitor` — 중복 이름 `CompetitorAlreadyExistsError`.
- `list_competitors(session, *, only_enabled=False) -> list[Competitor]`.
- `get` / `get_or_raise` (`CompetitorNotFoundError`).
- `update(session, id, CompetitorUpdate)` / `disable` / `remove`.
- `load_aliases(row) -> list[str]` — JSON 파싱, 톨러런트(interests.load_keywords 패턴).
- `_dump_aliases(aliases)` — strip + JSON.

### `schemas.py`

```python
class CompetitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list)
    enabled: bool = True

class CompetitorUpdate(BaseModel):   # extra="forbid", all optional
    name: str | None; aliases: list[str] | None; enabled: bool | None

class CompetitorRead(BaseModel):     # from_attributes
    id; name; aliases: list[str]; enabled; created_at

@dataclass(frozen=True, slots=True)
class Headline:
    title: str
    url: str
    importance: float

@dataclass(frozen=True, slots=True)
class CompetitorMentions:
    name: str
    count: int
    headlines: list[Headline]   # importance desc, truncated to top_k

@dataclass(frozen=True, slots=True)
class CompetitorReport:
    since: date
    until: date            # exclusive
    total_items: int       # items scanned in window
    competitors: list[CompetitorMentions]   # all enabled, count desc then name
```

### `service.py` (DB)

```python
def analyze_competitors(
    session, *, days: int = 7, until: date | None = None,
    since: date | None = None, top_k: int = 5,
) -> CompetitorReport: ...
```

- 윈도우: `until`(exclusive 상한, 기본 오늘+1일 = 오늘 포함), `since` = `until - days`
  (또는 명시 `since`). 앵커 `published_at`→`created_at`, naive UTC 비교(SQLite).
- 활성 경쟁사 로드 → `CompetitorProfile`(별칭 소문자 튜플).
- 윈도우 내 ProcessedItem⋈RawItem 조회. 각 아이템 `text_lower = (title + " " + summary).lower()`.
  `mentioned_competitor_ids`로 매칭된 경쟁사마다 `Headline(normalized_title, canonical_url,
  importance_score)` 누적.
- 경쟁사별 헤드라인 importance 내림차순 정렬·top_k 절단, 카운트 집계.
- `CompetitorReport`(활성 경쟁사 전부 포함, 0건 경쟁사도 워치리스트로; count desc, 동률 name).

### `report.py` (순수)

```python
def render_markdown(report: CompetitorReport) -> str: ...
```

- 헤더(기간 `since ~ until`, 스캔 기사 수). 경쟁사별 `## {name} — {count}건`.
- 헤드라인: `- [{title}]({url})` (importance순). 0건이면 `(언급 없음)`.
- 경쟁사 0개면 호출 전에 서비스/CLI가 빈 리스트 → CLI가 안내.

### `cli.py` — `newsletter competitors`

다중 명령 Typer(`add_completion=False, no_args_is_help=True`):
- `add --name --aliases "a,b,c"` / `list` / `remove ID` / `enable ID` / `disable ID`
  (interests CLI 톤·메시지 패턴).
- `report [--days N | --since YYYY-MM-DD] [--until YYYY-MM-DD] [--top K] [--save PATH]`.
  경쟁사 0개 등록 시 "(no competitors registered)" 안내.
- 루트 등록: `app.add_typer(competitors_app, name="competitors")`.

---

## 윈도우 / 매칭 세부

- 단일 룩백 윈도우. `until` exclusive 상한(기본 오늘+1일), `since` 포함 하한. `--days`와
  `--since`가 함께 오면 `--since` 우선. half-open `[since, until)`.
- 앵커: `published_at` 우선, NULL이면 `created_at`. SQLite naive 비교(trends와 동일 철학).
- 한 아이템이 여러 경쟁사 별칭에 매칭되면 각 경쟁사에 모두 귀속.

---

## 회귀 안전

- 새 슬라이스 + 새 테이블. 기존 스코어링·처리·작성·트렌드 경로 무변경.
- 경쟁사 0개 / 윈도우 빈 경우 → 빈 리포트/안내. 마이그레이션은 additive·reversible.

---

## 테스트 계획 (~21)

| 대상 | 개수 | 핵심 케이스 |
|---|---|---|
| `matching` | ~5 | ASCII 단어경계("meta"≠"metadata"), 한글 부분문자열(조사 결합), 다중 매칭, 대소문자 무시, 빈 별칭 무시 |
| `repository` | ~5 | add/중복 에러, list 활성 필터, update, disable/remove, load_aliases 톨러런트 |
| `service` | ~4 | 윈도우 필터, 다중 경쟁사 귀속, 비활성 제외, published_at NULL→created_at 폴백 |
| `report` | ~3 | 경쟁사별 카운트·헤드라인(importance순), 0건 "(언급 없음)", 헤더 기간 |
| `cli` | ~4 | add+list, report 스모크, 미등록 안내, report --save 파일 |

- 서비스/CLI 테스트는 `RawItem.source_id` NOT NULL이므로 Source를 먼저 시드. 실제 외부 호출 없음.

---

## 구현 순서 (슬라이스 단위 커밋)

1. `matching.py` + 테스트(순수, 의존 0 — `CompetitorProfile`는 matching에 정의).
2. `models/competitor.py` + `models/__init__` 등록 + 마이그레이션.
3. `schemas.py` + `repository.py` + 테스트.
4. `service.py` + 테스트.
5. `report.py` + 테스트.
6. `cli.py` + 루트 등록 + 테스트.
7. `AGENTS.md` 갱신 + 전체 검증.

각 단계: 실패 테스트 → 최소 구현 → 통과 → 커밋.

---

## 주요 파일

| 종류 | 경로 |
|---|---|
| 신규 모델 | `src/newsletter/models/competitor.py` |
| 신규 슬라이스 | `src/newsletter/slices/competitors/{matching,repository,schemas,service,report,cli}.py` |
| 수정 | `src/newsletter/models/__init__.py`, `src/newsletter/cli.py`, `AGENTS.md` |
| 마이그레이션 | `migrations/versions/<rev>_add_competitors_table.py` |
