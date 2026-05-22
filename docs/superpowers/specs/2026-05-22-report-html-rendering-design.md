# 리포트 HTML 렌더링 (공용) — 1단계

> 설계 문서. 진실 공급원: `plan/ai_newsletter_service_plan.md` §25 Phase 3(자동 리포트),
> 승인 플랜 `C:\Users\user\.claude\plans\wondrous-cooking-quill.md`. 작성일 2026-05-22.

---

## 한 줄 요약

리포트 마크다운을 보기 좋은 **자체 완결형 HTML 문서**로 감싸는 공용 렌더러를 `core`에
추가하고, 기존 `trends`·`competitors` 리포트 CLI에 `--format md|html` 출력 옵션을 붙인다.
마크다운은 그대로 검증 가능한 원본으로 두고, HTML은 `markdown-it-py`로 파생한다.

이는 "더 가시성 좋은 리포트" 작업의 1단계다. 2단계(월간 AI 동향 리포트)는 별도
설계·플랜 사이클로 진행하며 본 렌더러를 재사용한다.

---

## 목표 / 비목표

**목표**
- 리포트 마크다운 → 스타일이 적용된 단일 HTML 문서로 변환하는 공용 순수 함수.
- `trends`와 `competitors report` CLI에 `--format md|html` 추가(기본 `md`).
- 외부 리소스(CDN·외부 CSS/JS) 0 — 파일 하나로 공유·오프라인·이메일 친화.
- 기존 동작 무변경(기본 `md`) — 회귀 0.

**비목표 (YAGNI)**
- 월간 AI 동향 리포트(2단계, 별도 사이클).
- 리포트별 전용 Jinja2 HTML 템플릿(마크다운 우회) — "마크다운 원본" 모델과 어긋남.
- 확장자 기반 포맷 자동 추론(`.html`→html) — 명시적 `--format`이 예측 가능.
- 뉴스레터 이메일 본문 HTML(이미 `assembler.py`가 담당) 통합·대체.
- 테마 커스터마이즈 옵션·다중 테마 — 합리적 기본 하나.

---

## 결정 사항 (브레인스토밍 합의)

1. **접근**: 마크다운 → `markdown-it-py`로 HTML 조각 변환 후, 임베디드 CSS를 가진 자체
   완결형 HTML 문서로 래핑. (전용 HTML 템플릿/외부 CSS 프레임워크 안 씀.)
2. **위치**: `src/newsletter/core/report_html.py` — trends·competitors·(향후)월간이 공유하는
   횡단 기능(`core/text.py`가 corpus·trends에 공유되는 패턴과 동일).
3. **CLI**: `--format md|html` 옵션(기본 `md`). stdout·`--save` 모두 선택 포맷 따름.
4. **마크다운 원본 유지**: 각 리포트의 `render_markdown()`은 그대로. HTML은 그 출력을 감쌀 뿐.
5. **스타일**: 깔끔한 단일 테마(최대폭 제한·읽기 좋은 타이포·줄무늬 표·섹션 색 헤더·인쇄
   친화). 합리적 기본을 잡고 추후 조정.

---

## 컴포넌트 — `src/newsletter/core/report_html.py`

순수 모듈. IO·DB·LLM 없음.

```python
def render_report_html(markdown_body: str, *, title: str) -> str:
    """Wrap a report's markdown body in a self-contained, styled HTML document.

    Converts ``markdown_body`` to an HTML fragment with markdown-it (commonmark
    + linkify) and embeds it in a full ``<!DOCTYPE html>`` document whose
    ``<head>`` carries ``<title>`` and an inline ``<style>`` block. No external
    CSS/JS — the result is a single portable file.
    """
```

- 변환기: `MarkdownIt("commonmark", {"html": False}).enable("table")`.
  - `html=False`는 명시 지정해야 한다 — commonmark 프리셋의 기본은 `html=True`(원시 HTML
    통과)다. 피드에서 온 기사 제목이 그대로 본문에 들어가므로(`competitors/report.py`),
    `html=False`로 원시 태그를 이스케이프해 XSS를 막는다(조립기 `assembler.py:51`과 동일 컨벤션).
  - `table` 룰을 명시 활성 — commonmark 프리셋엔 GFM 파이프 표가 없다. `gfm-like` 프리셋은
    `linkify-it-py`(미설치)를 요구해 쓰지 않는다. 리포트는 명시적 `[text](url)` 링크만 써서
    linkify 불필요.
- `title`은 `<head><title>`에만 사용(브라우저 탭/문서 제목). 본문 H1은 마크다운에서 옴.
  → `title`은 HTML 이스케이프 처리(`html.escape`)해서 주입.
- 임베디드 CSS(모듈 상수 `_STYLE`): `max-width` 제한 + 중앙 정렬, 시스템 폰트 스택,
  `table { border-collapse }` + 줄무늬(`tr:nth-child(even)`), `th` 배경, `h1/h2` 하단 보더,
  `a` 색상, `@media print` 보정. 외부 URL 0.
- 반환: `"<!DOCTYPE html>\n<html ...>...</html>\n"` 완성 문서 문자열.
- `__all__ = ["render_report_html"]`.

### 의존성

`markdown-it-py`는 이미 설치되어 사용 중(`assembler.py`). 새 의존성 추가 없음.

---

## CLI 변경

### `trends` — `src/newsletter/slices/trends/cli.py`

현재 `invoke_without_command` 단일 콜백. 옵션 추가:

- `format: str = typer.Option("md", "--format", help="md or html.")`
- 검증: `format`이 `{"md","html"}` 아니면 `typer.echo(... err=True)` + `raise typer.Exit(1)`
  (기존 `period` 검증과 동일 톤).
- 빈 윈도우 안내(`(no items in window)`)는 현행 유지(포맷 무관, 데이터 없음 우선).
- 본문 생성: `markdown = render_markdown(report)` (현행).
- `format == "html"`이면 `output = render_report_html(markdown, title=f"트렌드 리포트 — {period}")`,
  아니면 `output = markdown`.
- `--save`면 `Path(save).write_text(output, encoding="utf-8")` + 저장 안내, 아니면 `typer.echo(output)`.

### `competitors` — `src/newsletter/slices/competitors/cli.py` (`report` 명령)

동일 패턴:
- `report`에 `--format md|html`(기본 `md`) 추가.
- 미등록 안내(`(no competitors registered)`)는 현행 유지(포맷 무관).
- `markdown = render_markdown(report)` 후 `format`에 따라 `render_report_html(markdown,
  title="경쟁사 멘션 리포트")`로 감싸거나 그대로.
- `--save`/stdout 분기 현행 유지(선택 포맷 기록).

> 두 CLI 모두: `--format` 미지정 시 기본 `md` → 기존 출력·기존 테스트 100% 불변.

---

## 데이터 흐름

```
report 객체 ──render_markdown()──▶ 마크다운(검증 원본)
                                      │
                       format=="html"? │
                         ├─ yes ─▶ render_report_html(md, title) ─▶ HTML 문서
                         └─ no  ─▶ 마크다운 그대로
                                      │
                          --save? ──┬─ yes ─▶ 파일(utf-8)
                                    └─ no  ─▶ stdout
```

---

## 회귀 안전

- 기본 `--format md`라 기존 trends·competitors 동작·테스트 무변경.
- 새 모듈 + 두 CLI에 옵션 1개씩 추가. 다른 슬라이스·파이프라인 무관.
- 새 외부 의존성 없음. 외부 호출 없음.

---

## 테스트 계획 (~9)

| 대상 | 개수 | 핵심 케이스 |
|---|---|---|
| `core/report_html` | ~4 | (a) `<!DOCTYPE html>`로 시작, (b) `<title>` 주입·이스케이프, (c) 마크다운 표→`<table>`·H1→`<h1>`, (d) `<style>` 임베디드 & 외부 `http(s)` 리소스 0(자체 완결) |
| trends CLI | ~2 | `--format html` 출력이 HTML 문서; 기본 `md` 출력 불변(회귀) |
| competitors CLI | ~2 | `report --format html --save out.html` → 파일이 HTML 문서; 기본 `md` 불변 |
| 잘못된 format | ~1 | `--format xml` → exit 1 + 메시지 |

- 모든 테스트 결정적(markdown-it 결정적, 외부 호출 0).

---

## 구현 순서 (슬라이스 단위 커밋)

1. `core/report_html.py` + 테스트(순수, 의존 0). 실패 테스트 → 최소 구현 → 통과 → 커밋.
2. `trends/cli.py`에 `--format` + HTML 분기 + 테스트.
3. `competitors/cli.py` `report`에 `--format` + HTML 분기 + 테스트.
4. `AGENTS.md` 명령표 갱신(trends·competitors에 `[--format md|html]` 표기) + 전체 검증.

각 단계: 실패 테스트 → 최소 구현 → 통과 → 커밋.

---

## 주요 파일

| 종류 | 경로 |
|---|---|
| 신규 | `src/newsletter/core/report_html.py` |
| 수정 | `src/newsletter/slices/trends/cli.py`, `src/newsletter/slices/competitors/cli.py`, `AGENTS.md` |
| 신규 테스트 | `tests/core/test_report_html.py` (+ 기존 trends·competitors CLI 테스트에 케이스 추가) |
</content>
