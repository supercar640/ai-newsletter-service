# 부서별 다이제스트 (department digest) — Phase 3

> 설계 문서. 진실 공급원: `plan/ai_newsletter_service_plan.md` §25 Phase 3(부서별 맞춤
> 뉴스레터 — 독자 그룹별 콘텐츠 자동 구성), 승인 플랜
> `C:\Users\user\.claude\plans\wondrous-cooking-quill.md`. 작성일 2026-05-22.

---

## 한 줄 요약

운영자가 등록한 부서마다 그 부서 설명(description)에 가장 관련 있는 누적 기사를 골라
보여주는 **독립 다이제스트 리포트**(CLI + 마크다운 + HTML)를 생성한다. 관련도는 임베딩
의미 매칭(코사인)으로, 키/임베딩이 없으면 키워드 오버랩으로 폴백한다. 발송·수신자 인프라는
건드리지 않는다(스펙 §21이 "부서별 분기 발송 — 초기엔 통합본으로 충분"으로 보류).

---

## 배경 / 기존 구현과의 차별

- **audiences**(general/executive/technical): 독자 그룹별 *표현*(분량·템플릿) 변형 — 콘텐츠
  선별은 안 함. (이미 구현)
- **department_tips**: 부서마다 한 줄 활용 팁을 *통합본*에 주입. (이미 구현)
- **이 기능(신규)**: 부서마다 *콘텐츠(기사) 자체*를 관련도로 선별한 부서별 리포트. 표현 변형도
  팁 주입도 아닌 "부서별 콘텐츠 자동 구성"(Phase 3 정의)에 해당.

---

## 목표 / 비목표

**목표**
- 활성 부서별로 윈도우 내 ProcessedItem을 부서 관련도 순으로 top_k 선별.
- 관련도: 임베딩 코사인(부서 description ↔ ProcessedItem), 임베딩/키 없으면 키워드 오버랩 폴백.
- 마크다운 원본 + `--format html`(`core/report_html` 재사용).
- 데이터/부서 없으면 우아하게 안내(회귀 0).

**비목표 (YAGNI)**
- 수신자↔부서 매핑·부서별 발송/라우팅(스펙 §21 명시 보류 — 별도 수신자 인프라 필요).
- 부서별 NewsletterIssue 변형·검수/승인 파이프라인 편입(독립 리포트로 한정).
- Department에 임베딩 컬럼 추가(마이그레이션) — 부서 임베딩은 실행마다 온디맨드 계산.
- LLM 서술(트렌드/경쟁사처럼 결정적 데이터만). audiences/department_tips 변경.

---

## 결정 사항 (브레인스토밍 합의)

1. **스코프**: 부서별 콘텐츠 선별(표현 변형·팁은 기존). 발송/수신자 인프라 제외.
2. **산출물**: 독립 다이제스트 리포트(마크다운 + HTML). NewsletterIssue·검수·발송 무관.
3. **관련도**: 임베딩 의미 매칭 + 키워드 폴백. 부서 임베딩은 온디맨드(마이그레이션 없음).
4. **배치**: 새 top-level 슬라이스가 아니라 **기존 `departments` 슬라이스에 추가**(응집성).
   `newsletter departments digest` 서브커맨드.

---

## 배치 / 슬라이스 변경 — `src/newsletter/slices/departments/`

기존 registry(CRUD + seeds + tips 연계)는 그대로. 다음을 추가한다.

```
departments/
  ...(기존: repository.py, schemas.py, cli.py, seeds.py)
  relevance.py    # 순수: 키워드 오버랩 점수 + 코사인 래핑, 모드 판정
  digest.py       # DB+임베딩: 윈도우 조회 → 부서별 랭킹 → DepartmentDigest
  report.py       # 순수: DepartmentDigest → 마크다운
```
`schemas.py`에 다이제스트 dataclass를 추가하고, `cli.py`에 `digest` 명령을 추가한다.

### `schemas.py` 추가분

```python
@dataclass(frozen=True, slots=True)
class RelevantHeadline:
    title: str
    url: str
    score: float

@dataclass(frozen=True, slots=True)
class DepartmentDigestEntry:
    name: str
    headlines: list[RelevantHeadline]   # score desc, top_k

@dataclass(frozen=True, slots=True)
class DepartmentDigest:
    since: date
    until: date                 # exclusive
    total_items: int            # window 내 스캔 기사 수
    mode: str                   # "embedding" | "keyword"
    departments: list[DepartmentDigestEntry]   # 활성 부서 순(Department.id)
```

(기존 `DepartmentCreate`/`DepartmentUpdate` 등 registry 스키마는 그대로.)

### `relevance.py` (순수, IO 없음)

```python
def keyword_score(dept_tokens: set[str], item_text_lower: str) -> int:
    """부서 토큰 중 기사 텍스트에 등장하는 토큰 수(오버랩 카운트)."""

def embedding_score(dept_vec: list[float], item_vec: list[float]) -> float:
    """core.embeddings.cosine 래핑. 둘 중 비면 0.0."""
```
- 토큰화는 `core/text.tokenize` 재사용. `dept_tokens`는 `tokenize(name + " " + description)`의 집합.

### `digest.py` (DB + 임베딩)

```python
def build_department_digest(
    session, *, days: int = 7, until: date | None = None,
    since: date | None = None, top_k: int = 5,
    embed_client: EmbeddingClient,
) -> DepartmentDigest: ...
```
- 윈도우: `until`(exclusive, 기본 오늘+1일), `since` = `until - days`(또는 명시). half-open.
- 활성 부서 로드(`repository.list_departments(only_enabled=True)`).
- 부서 임베딩: `embed_client.embed([dept_text for each dept])` 1배치. 결과가 비어 있으면(키 없음/
  `DisabledEmbeddingClient`) **키워드 모드**, 아니면 **임베딩 모드**. (모드는 실행마다 하나.)
- 윈도우 내 ProcessedItem⋈RawItem 조회: normalized_title, canonical_url, summary, embedding(bytes),
  published_at, created_at. 앵커(published_at→created_at, naive UTC) 윈도우 재확인(competitors와 동일).
  `total_items` = 스캔 수.
- 각 부서 × 각 아이템 점수:
  - 임베딩 모드: `embedding_score(dept_vec, deserialize(item.embedding))` (아이템 임베딩 없으면 0.0).
  - 키워드 모드: `keyword_score(dept_tokens, (title + " " + summary).lower())`.
- 부서별 점수 내림차순 정렬, **score > 0**만, top_k 절단 → `RelevantHeadline(title,url,score)`.
- `DepartmentDigest`(활성 부서 전부 포함 — 0건도 워치리스트; mode 기록).

### `report.py` (순수)

```python
def render_markdown(digest: DepartmentDigest) -> str: ...
```
- 헤더: `# 부서별 다이제스트`, 기간(`since ~ until`), 스캔 수, 모드(`(관련도: 임베딩|키워드)`).
- 부서별 `## {name}` + `- [{title}]({url})`(관련도순). 관련 기사 없으면 `(관련 기사 없음)`.
- 활성 부서 0개면 `(등록된 부서 없음)`.
- 결정적: `"\n".join(lines).rstrip() + "\n"`.

### `cli.py` — `newsletter departments digest`

기존 다중 명령 Typer에 추가:
- `digest [--days N | --since YYYY-MM-DD] [--until YYYY-MM-DD] [--top K] [--format md|html] [--save PATH]`.
- format 검증(친절 메시지+exit1), since/until은 `date.fromisoformat`.
- `embed_client = build_embedding_client()` (monitoring.recorder) 주입 → `build_department_digest(...)`.
- `render_markdown` → html이면 `render_report_html(md, title="부서별 다이제스트")` → save/stdout.
- (기존 add/list/remove/enable/disable/seed 무변경.)

---

## 관련도 / 윈도우 세부

- 모드는 실행 단위. 임베딩 모드는 부서·아이템 양쪽 벡터 필요(아이템 임베딩은 처리 시 생성됨).
  키워드 모드는 외부 호출 0·완전 결정적.
- 한 아이템이 여러 부서에 관련되면 각 부서에 모두 귀속(점수는 부서별 독립).
- 앵커·naive UTC 비교는 trends/competitors와 동일 철학.

---

## 회귀 안전

- 기존 departments registry·tips·audiences·발송 경로 무변경(읽기 전용 + 신규 명령).
- 새 테이블·마이그레이션·새 외부 의존성 없음. 발송 코드 없음(상태머신 가드 무관).
- 키 없으면 키워드 폴백으로 동작(임베딩 제공자 불필요).

---

## 테스트 계획 (~15)

| 대상 | 개수 | 핵심 케이스 |
|---|---|---|
| `relevance` | ~3 | 키워드 오버랩 카운트, 코사인 래핑(빈 벡터→0), 토큰 집합 |
| `digest` | ~5 | 키워드 모드 부서별 랭킹·top_k·점수0 제외, 임베딩 모드(가짜 embed_client) 코사인 랭킹, 윈도우 필터, 다부서 귀속, 빈 윈도우/부서 |
| `report` | ~3 | 부서 섹션·관련도순, 관련 기사 없음/등록 부서 없음, 헤더(기간·모드) |
| `cli` | ~4 | digest 스모크(키워드 모드), `--format html` 문서, `--save` 파일, 잘못된 format exit 1 |

- 서비스/CLI는 Source→RawItem→ProcessedItem + Department 시드. 테스트 환경은 키 없음 →
  키워드 모드 결정적. 임베딩 모드는 가짜 `embed_client`(고정 벡터) 주입으로 검증.

---

## 구현 순서 (슬라이스 단위 커밋)

1. `relevance.py` + 테스트(순수).
2. `schemas.py` 다이제스트 dataclass 추가 + `digest.py` + 테스트(키워드 모드 + 가짜 embed_client).
3. `report.py` + 테스트.
4. `cli.py` `digest` 명령 + 테스트.
5. `AGENTS.md`(명령표 + departments 설명 보강) + 전체 검증.

각 단계: 실패 테스트 → 최소 구현 → 통과 → 커밋.

---

## 주요 파일

| 종류 | 경로 |
|---|---|
| 신규 | `src/newsletter/slices/departments/{relevance,digest,report}.py` |
| 수정 | `src/newsletter/slices/departments/schemas.py`(dataclass 추가), `src/newsletter/slices/departments/cli.py`(digest 명령), `AGENTS.md` |
| 신규 테스트 | `tests/slices/departments/{test_relevance,test_digest,test_digest_report,test_digest_cli}.py` |
| 재사용(무수정) | `departments.repository`, `core.embeddings`(cosine/deserialize/EmbeddingClient), `core.text.tokenize`, `core.report_html`, `monitoring.recorder.build_embedding_client`, models(`Department`,`RawItem`,`ProcessedItem`) |
</content>
