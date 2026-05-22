# 성과 대시보드 (performance dashboard) — Phase 3

> 설계 문서. 진실 공급원: `plan/ai_newsletter_service_plan.md` §25 Phase 3(대시보드 —
> 소스별 성과·클릭률·품질 지표), 승인 플랜 `C:\Users\user\.claude\plans\wondrous-cooking-quill.md`.
> 작성일 2026-05-22.

---

## 한 줄 요약

운영자가 **소스별 성과**(수집/처리 건수, 평균 relevance·importance)와 **품질 지표**
(트랙 분리·상위 카테고리·중복 클러스터 효과)를 한눈에 보는 독립 리포트(CLI + 마크다운 +
HTML)를 생성한다. 기존 데이터만으로 계산하며(LLM·새 테이블 없음), 단일 룩백 윈도우에서
매번 재계산한다. `newsletter stats`(운영/토큰/비용)와 상호 보완한다.

---

## 목표 / 비목표

**목표**
- 소스별 수집(RawItem) 대비 처리(ProcessedItem) 건수와 평균 품질 점수.
- 전체 품질 요약: 트랙(expert/practical) 분리, 상위 카테고리, 중복 클러스터 효과.
- 마크다운 원본 + `--format html`(1단계 `core/report_html` 재사용).
- 데이터 없으면 우아하게 안내(회귀 0 — 기존 동작 무변경).

**비목표 (YAGNI)**
- **클릭률·오픈율·독자 인게이지먼트** — 추적 인프라(이벤트 테이블·링크 래핑·오픈 픽셀·
  웹훅·이메일 공급자 연동)가 전혀 없어 현 데이터로 계산 불가. 별도의 큰 프로젝트로 분리.
- 운영 지표(스텝 성공/실패·토큰·비용) — 이미 `newsletter stats`(RunLog)가 담당. 중복 회피.
- "뉴스레터 채택 건수"(NewsletterIssue.candidate_ids_json 파싱) — v1 제외, 추후 추가 가능.
- 새 테이블·마이그레이션·LLM·임베딩.

---

## 결정 사항 (브레인스토밍 합의)

1. **스코프**: 소스별 성과 + 품질 지표만. 클릭률은 데이터 부재로 제외.
2. **독립 리포트**: trends·competitors·monthly와 동일 패턴(마크다운 + HTML, CLI).
3. **윈도우**: `RawItem.collected_at` 기준 단일 룩백(`--days`, 기본 30; `--since`/`--until`).
   collected_at은 NOT NULL이라 앵커 폴백 불필요.
4. **stats와 분리**: 대시보드 = 콘텐츠 성과(소스·품질), stats = 운영/비용. 중복 없음.

---

## 데이터 출처 (기존, 무수정)

- `Source`(source_id PK, name, content_track) — 소스 메타.
- `RawItem`(source_id FK, collected_at NOT NULL) — 수집 단위.
- `ProcessedItem`(raw_item_id FK, relevance_score, importance_score, content_track, category,
  duplicate_group_id) — 처리·품질. 소스 추적: ProcessedItem→RawItem.source_id→Source.

---

## 슬라이스 구조 — `src/newsletter/slices/dashboard/`

```
dashboard/
  __init__.py
  schemas.py    # SourceStat, QualitySummary, DashboardReport
  service.py    # 윈도우 집계 → DashboardReport
  report.py     # DashboardReport → 마크다운
  cli.py        # newsletter dashboard [--days N | --since/--until] [--format md|html] [--save]
```

### `schemas.py`

```python
@dataclass(frozen=True, slots=True)
class SourceStat:
    source_id: str
    name: str
    content_track: str
    collected: int
    processed: int
    avg_relevance: float   # 0.0 when processed == 0
    avg_importance: float

@dataclass(frozen=True, slots=True)
class QualitySummary:
    total_collected: int
    total_processed: int
    track_counts: dict[str, int]            # content_track -> processed count
    top_categories: list[tuple[str, int]]   # (category, count) desc, top_k
    distinct_groups: int                    # distinct non-null duplicate_group_id
    grouped_items: int                      # processed items carrying a duplicate_group_id

@dataclass(frozen=True, slots=True)
class DashboardReport:
    since: date
    until: date                # exclusive
    sources: list[SourceStat]  # collected desc, then name
    quality: QualitySummary
```

### `service.py` (DB)

```python
def build_dashboard(
    session, *, days: int = 30, until: date | None = None,
    since: date | None = None, top_categories: int = 10,
) -> DashboardReport: ...
```

- 윈도우: `until`(exclusive, 기본 오늘+1일), `since` = `until - days`(또는 명시 `since`). half-open
  `[since, until)` on `RawItem.collected_at`.
- 소스 메타 로드: `select(Source.source_id, Source.name, Source.content_track)` → dict.
- 윈도우 행 조회: `RawItem` LEFT JOIN `ProcessedItem`(raw_item_id) where collected_at in window.
  각 행 → source_id(항상), processed 여부 + relevance/importance/track/category/duplicate_group_id(처리됨일 때만).
- 소스별 집계: collected += 1; 처리됨이면 processed += 1, 점수 합산. avg = 합/processed(없으면 0.0).
- 품질 요약: total_collected = 행 수, total_processed = 처리된 행 수, track_counts·top_categories는
  처리된 행 기준, distinct_groups = 비-NULL duplicate_group_id의 distinct 수, grouped_items =
  duplicate_group_id 보유 처리 행 수.
- SourceStat: 윈도우에 수집 1건 이상인 소스만. 메타에 없는 source_id는 name=source_id, track="?".
  정렬 collected desc, 동률 name asc.

### `report.py` (순수)

```python
def render_markdown(report: DashboardReport) -> str: ...
```

- 헤더: `# 성과 대시보드`, 기간(`since ~ until`).
- `## 소스별 성과` — 표 `| 소스 | 트랙 | 수집 | 처리 | 평균 relevance | 평균 importance |`
  (소수 둘째 자리). 소스 0개면 `(데이터 없음)`.
- `## 품질 요약` — 전체 수집/처리; 트랙 분리(`expert_news: N, practical_insight: M`);
  중복(`처리 N건 중 그룹화 G건 / 고유 그룹 D개`); `상위 카테고리` 표(category, count). 처리 0건이면
  각 항목 `(없음)`.
- 결정적: `"\n".join(lines).rstrip() + "\n"`.

### `cli.py` — `newsletter dashboard`

단일 콜백(trends CLI 톤):
- `--days N`(기본 30), `--since YYYY-MM-DD`, `--until YYYY-MM-DD`, `--top K`(기본 10, 상위 카테고리 수),
  `--format md|html`(기본 md), `--save PATH`.
- format 검증 → 친절 메시지 + exit 1. since/until은 `date.fromisoformat`.
- `build_dashboard(...)` → `render_markdown` → `--format html`이면 `render_report_html(md,
  title="성과 대시보드")` → `--save`/stdout.
- 루트 등록: `app.add_typer(dashboard_app, name="dashboard")`.

---

## 회귀 안전

- 새 슬라이스. 기존 수집·처리·작성·trends·competitors·monthly 경로 무변경(읽기 전용).
- 새 테이블·마이그레이션·외부 의존성 없음. 발송 코드 없음(상태머신 가드 무관).
- 데이터/소스 없으면 빈 안내.

---

## 테스트 계획 (~13)

| 대상 | 개수 | 핵심 케이스 |
|---|---|---|
| `service` | ~5 | 소스별 collected/processed/평균 점수, 미처리 RawItem(LEFT JOIN) 반영, 윈도우 필터, 품질 요약(트랙·카테고리·중복), 빈 윈도우 |
| `report` | ~4 | 소스 표 렌더, 품질 요약 렌더, 빈 데이터 `(데이터 없음)`/`(없음)`, 헤더 기간 |
| `cli` | ~4 | 스모크, `--format html` 문서, `--save` 파일, 잘못된 format exit 1 |

- 서비스/CLI는 Source→RawItem→ProcessedItem 시드. 실제 외부 호출 없음.

---

## 구현 순서 (슬라이스 단위 커밋)

1. `schemas.py` + `service.py` + 테스트.
2. `report.py` + 테스트.
3. `cli.py` + 루트 등록 + 테스트.
4. `AGENTS.md`(명령표 + 슬라이스 트리) + 전체 검증.

각 단계: 실패 테스트 → 최소 구현 → 통과 → 커밋.

---

## 주요 파일

| 종류 | 경로 |
|---|---|
| 신규 슬라이스 | `src/newsletter/slices/dashboard/{schemas,service,report,cli}.py` + `__init__.py` |
| 수정 | `src/newsletter/cli.py`, `AGENTS.md` |
| 재사용(무수정) | `core.report_html.render_report_html`, models(`Source`,`RawItem`,`ProcessedItem`) |
</content>
