# 회사 관심사 RAG — 사내 문서 코퍼스 기반 스코어링 보강 (Phase 3)

> 설계 문서. 진실 공급원: `plan/ai_newsletter_service_plan.md` §25 Phase 3, 승인 플랜
> `C:\Users\user\.claude\plans\wondrous-cooking-quill.md`.
> 작성일 2026-05-21.

---

## 한 줄 요약

운영자가 손으로 큐레이션하는 `CompanyInterest`(키워드 + 임베딩 1개)를 넘어, **사내 문서
디렉터리**를 청크 단위로 인덱싱해 뉴스 아이템과의 의미적 관련도를 계산하고, 중요도
스코어에 추가 배수로 반영합니다. 임베딩 키가 없으면 키워드 겹침으로 폴백합니다.

플랜 §25 발전 순서(1차 고도화 = 중요도 점수 → 2차 고도화 = 회사 관심사 기반 RAG)와
일치하며, 스코어링 보강이 1차 목적입니다(뉴스레터 작성 프롬프트는 무변경).

---

## 목표 / 비목표

**목표**
- 사내 문서(로컬 `.md`/`.txt`)를 코퍼스로 인덱싱(증분 재인덱싱 포함).
- 뉴스 아이템 ↔ 코퍼스 의미 매칭으로 중요도 스코어를 보강.
- 임베딩 키 없을 때 키워드 겹침 폴백으로 부분 동작.
- 미설정/청크 0개 시 **완전 no-op**(회귀 0).

**비목표 (YAGNI)**
- 뉴스레터 작성 LLM 프롬프트에 사내 맥락 주입(별도 "작성 보강" 슬라이스로 분리 가능).
- Notion·외부 소스 연동(이번엔 로컬 디렉터리만).
- GraphRAG·KG·청크 간 관계 그래프(플랜상 장기 고도화).
- 청크별 가중치(보강 강도는 전역 상수 하나).
- de-boost(off-topic 감점) — 기존 interests처럼 **boost-only** 유지.

---

## 결정 사항 (브레인스토밍 합의)

1. **RAG 적용 지점**: 스코어링 보강. 작성 프롬프트 무변경.
2. **코퍼스 출처**: 로컬 파일 디렉터리(`COMPANY_CONTEXT_DIR`). 외부 의존 없음, 로컬-퍼스트
   SQLite 구조와 일치, Git 버전 관리 가능(단 비밀 문서는 운영자 책임).
3. **임베딩 키 없을 때**: 키워드 폴백. 기존 interests 키워드 매칭 패턴과 동일.
4. **아키텍처**: 새 독립 슬라이스 `corpus`. interests(명시 키워드)와 corpus(문서 의미
   매칭)는 **별개의 합성 가능한 신호**. 기존 스코어링/interests 테이블 무변경.

---

## 데이터 모델 — `src/newsletter/models/context_chunk.py`

`context_chunks` 테이블. 사내 문서 한 청크 = 한 행.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | int PK | |
| `source_path` | str(500) | 코퍼스 디렉터리 기준 파일 상대 경로 (문자열 보존) |
| `file_hash` | str(64) | 파일 전체 내용 해시. 같은 파일의 모든 청크가 공유 → 증분 재인덱싱 키 |
| `chunk_index` | int | 파일 내 청크 순서 |
| `text` | Text | 청크 본문 |
| `keywords_json` | Text | 폴백용 추출 키워드 JSON 배열(소문자) |
| `embedding` | LargeBinary nullable | 임베딩 BLOB(없으면 NULL) |
| `embedding_model` | str(64) nullable | |
| `created_at` | DateTime(tz) | server_default now() |

- 유니크 제약: `(source_path, chunk_index)` → `uq_context_chunks_path_index`.
- per-chunk weight 없음. 보강 강도는 스코어링 모듈 상수.
- 마이그레이션: Alembic autogenerate, `context_chunks` 신규 테이블.

---

## 슬라이스 구조 — `src/newsletter/slices/corpus/`

```
corpus/
  __init__.py
  chunking.py     # 순수: 파일 텍스트 → 청크 + 키워드 추출
  repository.py   # 순수 DB 함수
  indexer.py      # 오케스트레이션(스캔 → 해시 비교 → 임베딩 → 영속화)
  schemas.py      # IndexReport, ChunkRead
  cli.py          # newsletter corpus index/list/clear/status
```

### `chunking.py` (순수, IO 없음)

- `chunk_text(text: str, *, max_chars: int = 1200) -> list[str]`
  - 마크다운 헤딩(`#`~`######`) 경계 + 빈 줄 문단 경계로 1차 분할.
  - 한 블록이 `max_chars` 초과 시 문장/공백 경계로 추가 분할.
  - 빈 청크 제거.
- `extract_keywords(text: str, *, max_keywords: int = 20) -> list[str]`
  - 소문자화 → 단어 토큰화(한글/영문/숫자) → 길이 1 토큰·간단 불용어 제거 → 빈도순
    상위 N개. 결정적(동률은 사전순).

### `repository.py` (순수 DB 함수, Session 인자)

- `file_hashes(session) -> dict[str, str]` — `{source_path: file_hash}`(증분 비교용).
- `replace_file_chunks(session, *, source_path, file_hash, chunks)` — 해당 파일의 기존
  청크 삭제 후 새 청크 일괄 삽입. 멱등(같은 입력 재실행 시 동일 상태).
  `chunks`는 `ChunkInsert`(text, keywords, embedding bytes|None, model|None) 시퀀스.
- `list_chunks(session) -> list[ContextChunk]`.
- `delete_all(session) -> int` — 전체 삭제(반환=삭제 행 수).
- `load_keywords(row) -> list[str]` — JSON 파싱(interests와 동일 톨러런트 패턴).

### `indexer.py` (오케스트레이션)

```python
@dataclass
class IndexReport:
    scanned: int      # 디렉터리에서 발견한 파일 수
    indexed: int      # (재)인덱싱한 파일 수
    skipped: int      # 해시 동일로 건너뛴 파일 수
    chunks: int       # 인덱싱 결과 총 청크 수(이번에 쓴 것)
    embedded: int     # 임베딩이 붙은 청크 수

def index_corpus(session, *, root: Path, embed_client) -> IndexReport: ...
```

- `root` 하위 `*.md`, `*.txt` 스캔(재귀). 각 파일 내용 읽어 해시 계산.
- 저장된 해시와 동일 → skip. 다르거나 신규 → `chunk_text` + `extract_keywords`.
- 변경된 모든 파일의 청크 텍스트를 **한 번에** `embed_client.embed([...])` 배치 호출.
  반환 빈 리스트(DisabledEmbeddingClient)면 embedding=None로 저장(키워드만).
- `replace_file_chunks`로 파일 단위 교체.
- 사라진 파일(저장됐으나 디렉터리에 없음) 처리: 이번 슬라이스에선 `corpus clear` 후
  재인덱싱을 정석으로 두고, 인덱서가 자동 삭제까지 하진 않음(YAGNI; status로 노출).

### `cli.py` — `newsletter corpus ...`

- `index` — `COMPANY_CONTEXT_DIR` 스캔·인덱싱. 미설정 시 경고 후 no-op exit.
  `build_embedding_client()`(monitoring.recorder) 재사용.
- `list` — 파일별 청크 수 / 임베딩 유무 요약.
- `clear` — 전체 청크 삭제(확인 플래그 또는 즉시; interests `remove` 톤과 맞춤).
- `status` — 디렉터리 vs DB 상태(신규/변경/삭제 파일 카운트), 임베딩 키 유무.
- 루트 등록: `app.add_typer(corpus_app, name="corpus")`. 다중 명령이라 `newsletter
  corpus index`로 직접 호출됨(send/slack의 중첩 quirk 없음).

---

## 스코어링 통합 — `src/newsletter/slices/integration/scoring.py`

기존 `interest_match_factor`와 나란히 추가(파일 응집성 유지 — 이미 trust/recency/llm/
interest 신호를 모두 담음).

```python
@dataclass(frozen=True, slots=True)
class CorpusChunk:
    keywords: tuple[str, ...]            # 소문자
    embedding: Sequence[float] | None

_CORPUS_CAP: Final = 0.3                 # interests 0.5보다 보수적(두 보강이 곱해짐)
_CORPUS_COSINE_THRESHOLD: Final = 0.55
_CORPUS_KEYWORD_SATURATION: Final = 3    # distinct 키워드 N개 적중 → full strength

def corpus_relevance_factor(
    *, title, summary, item_embedding, chunks: list[CorpusChunk]
) -> float:
    # 청크 없음 → 1.0
    # 임베딩 경로: 청크 전체 max 코사인 c, c >= threshold면
    #   strength = (c - threshold) / (1 - threshold)
    # 폴백(item_embedding 없음 또는 모든 청크 embedding None):
    #   text에 등장하는 distinct 코퍼스 키워드 수 hits,
    #   strength = min(1.0, hits / SATURATION)
    # return 1.0 + strength * _CORPUS_CAP   # [1.0, 1.3]
```

- 임베딩과 키워드 폴백은 **상호 배타**가 아니라, 임베딩 경로가 가능하면 우선하고 불가능할
  때 키워드 폴백. (interests는 둘 중 max를 쓰지만, corpus는 청크가 많아 키워드 합산이
  과해지므로 폴백 전용으로 단순화.)
- `score_items(...)`에 `corpus_chunks: list[CorpusChunk] | None = None` 인자 추가.
  base 계산을 `base × interest_match_factor × corpus_relevance_factor`로 확장.
  `corpus_chunks` None/빈 리스트면 1.0 → 회귀 0.

---

## 통합 서비스 — `src/newsletter/slices/integration/service.py`

- `_load_corpus_chunks(session) -> list[CorpusChunk]` — `corpus.repository.list_chunks`로
  로드, 키워드 소문자 튜플 + 임베딩 deserialize.
- `score_items(...)`에 `corpus_chunks` 전달. 뉴스 아이템 임베딩은 이미 로드 중인
  `embeddings` dict 재사용.
- `log.info("integration.done", ..., corpus_chunks=len(chunks))` 추가.

---

## 설정 — `src/newsletter/core/config.py`

```python
# 회사 관심사 RAG (Phase 3) — 사내 문서 코퍼스 디렉터리. 빈 값 = 기능 off.
company_context_dir: str = Field(default="")
```

- 임베딩은 기존 `voyage_*` 재사용(별도 키 없음).
- `.env.example`에 `COMPANY_CONTEXT_DIR=docs/company` 주석 예시 추가.

---

## 우아한 no-op / 회귀 안전

- `COMPANY_CONTEXT_DIR` 미설정 → `corpus index`가 경고 후 종료, 인덱싱 안 함.
- 청크 0개 → 스코어링에서 corpus 배수 1.0.
- 임베딩 키 없음 → 청크는 키워드만 저장, 폴백 매칭 동작.
- 기존 `interest_match_factor`·interests 테이블·작성 프롬프트 **무변경**.

---

## 테스트 계획 (TDD, 약 25개)

| 대상 | 개수 | 핵심 케이스 |
|---|---|---|
| `chunking` | ~6 | 헤딩 분할, 문단 분할, max_chars 초과 분할, 빈 청크 제거, 키워드 추출(빈도순·결정적), 불용어 제거 |
| `repository` | ~5 | replace 멱등, file_hashes, delete_all 반환수, load_keywords 톨러런트, 유니크 교체 |
| `indexer` | ~6 | 디렉터리 스캔, 미변경 skip, 변경 재인덱싱, fake 임베딩 배치, Disabled 폴백(embedding None), 빈 디렉터리 |
| `scoring` | ~6 | 빈 청크 1.0, 임베딩 max 코사인·임계 미만 1.0·스케일, 키워드 폴백 saturation, cap 클램프, score_items 합성 |
| `service` 통합 | ~2 | 청크 시드 후 importance 보강 적용, 청크 없을 때 무변화 |
| `cli` | ~3 | index(미설정 경고), list, clear |

- 테스트에서 실제 Voyage 호출 금지 — fake EmbeddingClient 주입.

---

## 구현 순서 (슬라이스 단위 커밋)

1. `chunking.py` + 테스트 (순수, 의존 0).
2. `models/context_chunk.py` + 마이그레이션.
3. `repository.py` + 테스트.
4. `indexer.py` + 테스트.
5. `scoring.corpus_relevance_factor` + `score_items` 인자 + 테스트.
6. `service` 통합 + 테스트.
7. `cli.py` + 루트 등록 + 테스트.
8. `config` + `.env.example` + `AGENTS.md` 갱신.

각 단계: 실패 테스트 → 최소 구현 → 통과 → 커밋.

---

## 주요 파일

| 종류 | 경로 |
|---|---|
| 신규 모델 | `src/newsletter/models/context_chunk.py` |
| 신규 슬라이스 | `src/newsletter/slices/corpus/{chunking,repository,indexer,schemas,cli}.py` |
| 수정 | `src/newsletter/slices/integration/{scoring,service}.py`, `core/config.py`, `cli.py`, `.env.example`, `AGENTS.md` |
| 마이그레이션 | `alembic/versions/<rev>_context_chunks.py` |
