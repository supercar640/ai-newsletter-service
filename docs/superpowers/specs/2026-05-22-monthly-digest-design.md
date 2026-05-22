# 월간 AI 동향 리포트 (monthly digest) — Phase 3

> 설계 문서. 진실 공급원: `plan/ai_newsletter_service_plan.md` §25 Phase 3(자동 리포트 —
> 월간 AI 동향 보고서), 승인 플랜 `C:\Users\user\.claude\plans\wondrous-cooking-quill.md`.
> 작성일 2026-05-22. 1단계(리포트 HTML 렌더링) 완료를 전제로 한다.

---

## 한 줄 요약

한 달치 누적 데이터를 **트렌드 + 경쟁사 동향 + 주요 기사**로 종합하고, 그 위에 LLM이
한국어 **서술 요약**을 얹은 월간 리포트를 생성한다. 결정적 데이터는 기존 `trends`·
`competitors` 서비스를 재사용하며, 출력은 마크다운 + HTML(1단계 `core/report_html` 재사용).
서술 섹션만 비결정적이고, LLM 비활성 시 우아하게 생략한다. 발송 없음(독립 리포트).

---

## 목표 / 비목표

**목표**
- 달력 기준 한 달 윈도우에서 트렌드·경쟁사·주요 기사를 한 문서로 종합.
- 결정적 데이터 위에 LLM 서술 요약("이번 달 요약") 1개 섹션.
- 마크다운 원본 + `--format html` 출력(1단계 렌더러 재사용).
- LLM 키 없음/실패 시 서술만 생략하고 나머지는 정상 출력(회귀 0, 기존 경로 무변경).

**비목표 (YAGNI)**
- 새 매칭/스코어링 로직(트렌드·경쟁사·중요도 점수는 기존 것 재사용).
- 이메일 발송·`NewsletterIssue` 영속화(리포트는 온디맨드, stdout/`--save`).
- 주간/분기 등 다른 주기(월간만).
- 관심사(interests) 전용 멘션 리포트(중요도 상위 기사로 대체 — 아래 결정 4).
- 기간 대비 증감 별도 계산(트렌드 섹션이 이미 직전 30일 대비 델타 제공).

---

## 결정 사항 (브레인스토밍 합의)

1. **범위**: 트렌드 + 경쟁사 + 관심사 종합.
2. **LLM 역할**: 결정적 데이터는 그대로 두고, 그 위에 서술 요약 섹션만 생성(검증 가능 유지).
3. **출력**: 마크다운 원본 + HTML 파생(1단계 `core/report_html.render_report_html`).
4. **"관심사 반영" 해석**: interests는 점수 부스트 레지스트리(별도 멘션 리포트 없음)이므로,
   그달 ProcessedItem을 `importance_score`(이미 관심사 부스트 반영) 내림차순 상위 N개로
   "주요 기사" 섹션을 구성한다.
5. **윈도우**: 달력 기준 월(`--month YYYY-MM`, 기본 = 직전 완료된 달). half-open `[월초, 다음달초)`.

---

## 슬라이스 구조 — `src/newsletter/slices/monthly/`

```
monthly/
  __init__.py
  schemas.py     # dataclass: TopHeadline, MonthlySection 묶음, MonthlyReport
  service.py     # 월 윈도우 집계 → MonthlyReport(narrative 제외)
  narrative.py   # MonthlyReport 데이터 → LLM(opus) 서술 문자열 | None
  report.py      # MonthlyReport(+narrative) → 마크다운
  cli.py         # newsletter monthly [--month YYYY-MM] [--format md|html] [--save PATH] [--no-narrative]
```
추가: `prompts/monthly/digest-narrative.md` (frontmatter 포함).

### `schemas.py`

```python
@dataclass(frozen=True, slots=True)
class TopHeadline:
    title: str
    url: str
    importance: float
    category: str | None

@dataclass(frozen=True, slots=True)
class MonthlyReport:
    month: str                       # "2026-04"
    since: date
    until: date                      # exclusive (다음 달 1일)
    total_items: int                 # 윈도우 내 스캔 기사 수
    trend: TrendReport               # trends.schemas.TrendReport 재사용
    competitors: CompetitorReport    # competitors.schemas.CompetitorReport 재사용
    top_headlines: list[TopHeadline] # importance desc, top_k
    narrative: str | None = None     # LLM 서술(없으면 None)
```

### `service.py` (DB)

```python
def build_monthly_report(
    session, *, month: date | None = None, top_k: int = 10,
) -> MonthlyReport: ...
```
- `month` = 대상 달의 임의 날짜(기본: 오늘 기준 직전 완료된 달의 1일). 내부에서 `since`=그 달 1일,
  `until`=다음 달 1일(exclusive)로 정규화.
- **트렌드**: `trends.service.analyze_trends(session, period="month", end=<until-1일>)` 재사용.
  (트렌드는 30일 롤링 윈도우·직전 30일 대비 비교라는 자체 의미를 유지 — 달력 월과 근사.)
- **경쟁사**: `competitors.service.analyze_competitors(session, since=since, until=until, top_k=5)` 재사용.
- **주요 기사**: 윈도우 내 ProcessedItem⋈RawItem를 앵커(`published_at`→`created_at`, naive UTC,
  competitors/trends와 동일 철학)로 필터 → `importance_score` 내림차순 top_k → `TopHeadline`
  (normalized_title, canonical_url, importance_score, category). 총 스캔 수 = `total_items`.
- `narrative`는 여기서 채우지 않음(None) — 서비스는 결정적·DB 전용 유지.

### `narrative.py` (LLM)

```python
def build_narrative(report: MonthlyReport, *, llm: LLMClient) -> str | None: ...
```
- `prompts/monthly/digest-narrative.md`(model opus) 로드 → 결정적 데이터 요약을 입력으로 렌더:
  떠오르는/신규 용어 상위, 경쟁사별 멘션 수, 주요 기사 **제목 + (요약 일부)**. **본문 전체 금지**
  (CLAUDE.md: title + raw_summary 우선). 입력은 JSON 직렬화해 프롬프트에 주입(expert writer 패턴).
- `llm.complete(body, model=prompt.model, max_tokens=2048)` 호출, 결과 텍스트 strip 반환.
- `LLMError` → `log.warning` 후 **None 반환**(우아한 생략, expert writer 폴백 철학과 동일).

### `report.py` (순수)

```python
def render_markdown(report: MonthlyReport) -> str: ...
```
- 헤더: `# {month} AI 동향 리포트`, 기간·스캔 수.
- `## 이번 달 요약` — `report.narrative` 있으면 그대로, 없으면 `(요약 생략 — LLM 비활성)`.
- `## 트렌드` — 떠오르는/신규/상위 용어(트렌드 데이터). 빈 경우 `(데이터 없음)`.
- `## 경쟁사 동향` — 경쟁사별 멘션 수 + 대표 헤드라인. 미등록/0건 우아 처리.
- `## 주요 기사` — `- [{title}]({url})` (importance순). 빈 경우 `(기사 없음)`.
- 결정적: `"\n".join(lines).rstrip() + "\n"` (trends·competitors report 패턴).

### `cli.py` — `newsletter monthly`

단일 콜백(trends CLI 톤):
- `--month YYYY-MM`(기본 직전 완료 달), `--top K`(기본 10), `--format md|html`(기본 md),
  `--save PATH`, `--no-narrative`(서술 생략 강제).
- 흐름: `build_monthly_report(session, month=..., top_k=...)` → 키 있고 `--no-narrative` 아니면
  `build_llm_client()`로 클라이언트 만들어 `build_narrative` 호출해 `report` 갱신(dataclass replace) →
  `render_markdown` → `--format html`이면 `render_report_html(md, title=f"{month} AI 동향 리포트")` →
  `--save`/stdout.
- LLM 키 판정: `get_settings().anthropic_api_key` 비었으면 서술 자동 생략(불필요한 실패 호출 회피).
- 루트 등록: `app.add_typer(monthly_app, name="monthly")` (`cli.py`).

---

## 윈도우 / 재사용 세부

- 달력 월 half-open `[since, until)`. `until` = 다음 달 1일(exclusive). 경쟁사·주요 기사는 이 윈도우로
  정확히 필터. 트렌드 섹션은 `analyze_trends(period="month", end=until-1일)`의 30일 윈도우 의미를 그대로
  사용(직전 30일 대비 델타) — 달력 월과 1~2일 근사. 단순·재사용 우선.
- 앵커·naive UTC 비교는 trends/competitors와 동일.

---

## 회귀 안전

- 새 슬라이스 + 새 프롬프트. trends·competitors·스코어링·작성 경로 무변경(읽기만 재사용).
- LLM 키 없음/실패 → 서술만 None, 나머지 정상. 발송 코드 없음(상태머신 가드 무관).
- 새 외부 의존성 없음.

---

## 테스트 계획 (~16)

| 대상 | 개수 | 핵심 케이스 |
|---|---|---|
| `service` | ~5 | 월 윈도우 정규화(기본=직전 달), 경쟁사/트렌드 집계 위임, 주요 기사 importance 내림차순·top_k 절단, 윈도우 밖 제외, 빈 데이터 |
| `narrative` | ~3 | 가짜 LLM 주입 시 서술 텍스트 반환, `LLMError`→None, 프롬프트 입력에 본문 전체 미포함(제목/요약만) |
| `report` | ~4 | 4개 섹션 렌더, narrative 없음→`(요약 생략…)`, 빈 트렌드/경쟁사/기사 우아 처리, 헤더 기간 |
| `cli` | ~4 | 스모크(기본 달), `--no-narrative`, `--format html` 문서, `--month` 지정 + `--save` 파일 |

- 서비스/CLI는 Source→RawItem→ProcessedItem 시드. LLM은 가짜 클라이언트 주입(실제 호출 0).
- 키 없는 기본 테스트 환경에서 narrative는 자연히 None → CLI 스모크가 결정적.

---

## 구현 순서 (슬라이스 단위 커밋)

1. `schemas.py`(+ 재사용 import) + `service.py` + 테스트.
2. `prompts/monthly/digest-narrative.md` + `narrative.py` + 테스트(가짜 LLM).
3. `report.py` + 테스트.
4. `cli.py` + 루트 등록 + 테스트.
5. `AGENTS.md`(명령표 + 슬라이스 트리) + 전체 검증.

각 단계: 실패 테스트 → 최소 구현 → 통과 → 커밋.

---

## 주요 파일

| 종류 | 경로 |
|---|---|
| 신규 슬라이스 | `src/newsletter/slices/monthly/{schemas,service,narrative,report,cli}.py` + `__init__.py` |
| 신규 프롬프트 | `prompts/monthly/digest-narrative.md` |
| 수정 | `src/newsletter/cli.py`, `AGENTS.md` |
| 재사용(무수정) | `trends.service.analyze_trends`, `competitors.service.analyze_competitors`, `core.report_html`, `core.llm`, `monitoring.recorder.build_llm_client`, `core.prompts.load_prompt` |
</content>
