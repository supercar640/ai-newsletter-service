# Report HTML Rendering (Stage 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared `core` renderer that wraps report markdown in a self-contained, styled HTML document, and give the `trends` and `competitors report` CLIs a `--format md|html` option.

**Architecture:** A pure function `core/report_html.py` converts a report's markdown body to an HTML fragment with `markdown-it-py` (GFM tables enabled) and embeds it in a full `<!DOCTYPE html>` document with an inline `<style>` block — no external resources. The two report CLIs keep their existing `render_markdown()` and only branch on a new `--format` option (default `md`, so existing behavior is unchanged).

**Tech Stack:** Python 3.12, Typer, `markdown-it-py` (already a dependency), pytest.

---

## Design Source

Full design: `docs/superpowers/specs/2026-05-22-report-html-rendering-design.md`. Brainstorming is complete — do not re-brainstorm. This is Stage 1 of the "richer reports" work; the monthly AI-trends report is a separate later cycle that will reuse this renderer.

## File Structure

| Kind | Path | Responsibility |
|---|---|---|
| Create | `src/newsletter/core/report_html.py` | Pure: markdown body → self-contained styled HTML document |
| Create (test) | `tests/core/test_report_html.py` | Unit tests for the renderer |
| Modify | `src/newsletter/slices/trends/cli.py` | Add `--format md\|html`, branch to HTML |
| Modify | `tests/slices/trends/test_cli.py` | Add HTML-format + bad-format tests |
| Modify | `src/newsletter/slices/competitors/cli.py` | Add `--format md\|html` to `report`, branch to HTML |
| Modify | `tests/slices/competitors/test_cli.py` | Add HTML-format + bad-format tests |
| Modify | `AGENTS.md` | Document `[--format md\|html]` on the two report commands |

---

### Task 1: core/report_html.py (pure renderer)

**Files:**
- Create: `src/newsletter/core/report_html.py`
- Test: `tests/core/test_report_html.py`

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_report_html.py`:

```python
"""core.report_html — markdown report body -> self-contained styled HTML."""

from __future__ import annotations

from newsletter.core.report_html import render_report_html

_SAMPLE = "# 트렌드 리포트\n\n| 용어 | 현재 |\n|---|---:|\n| sora | 3 |\n"


def test_returns_full_html_document():
    out = render_report_html(_SAMPLE, title="T")
    assert out.startswith("<!DOCTYPE html>")
    assert out.rstrip().endswith("</html>")


def test_title_is_injected_and_escaped():
    out = render_report_html(_SAMPLE, title="A & B <x>")
    assert "<title>A &amp; B &lt;x&gt;</title>" in out


def test_markdown_is_converted_including_tables():
    out = render_report_html(_SAMPLE, title="T")
    assert "<h1>트렌드 리포트</h1>" in out
    assert "<table>" in out
    assert "<td>sora</td>" in out


def test_is_self_contained_no_external_resources():
    # A URL-free body proves the WRAPPER (style/head) adds no external refs.
    out = render_report_html("# Hello\n\ntext only\n", title="T")
    assert "<style>" in out
    assert "http://" not in out
    assert "https://" not in out
    assert "<link" not in out
    assert "<script" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/test_report_html.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'newsletter.core.report_html'`

- [ ] **Step 3: Write minimal implementation**

Create `src/newsletter/core/report_html.py`:

```python
"""Render a report's markdown body as a self-contained, styled HTML document.

Reports across the app (trends, competitors, and future digests) produce
markdown as their canonical, testable form. This module wraps that markdown
in a single portable HTML file: markdown-it for the body, an inline
``<style>`` block for presentation, and zero external resources so the file
can be shared, viewed offline, or emailed as-is.

The ``gfm-like`` markdown-it preset is used (not strict ``commonmark``) so the
GFM pipe tables that reports emit render as real ``<table>`` elements.
"""

from __future__ import annotations

import html

from markdown_it import MarkdownIt

_MD = MarkdownIt("gfm-like")

_STYLE = """\
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
  line-height: 1.6;
  color: #1f2328;
  max-width: 820px;
  margin: 2rem auto;
  padding: 0 1.25rem;
}
h1 { font-size: 1.8rem; border-bottom: 2px solid #d0d7de; padding-bottom: .3rem; }
h2 {
  font-size: 1.35rem; border-bottom: 1px solid #d8dee4; padding-bottom: .25rem;
  margin-top: 2rem; color: #0969da;
}
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #d0d7de; padding: .4rem .6rem; text-align: left; }
th { background: #f6f8fa; }
tr:nth-child(even) td { background: #f6f8fa; }
a { color: #0969da; text-decoration: none; }
a:hover { text-decoration: underline; }
code { background: #eff1f3; padding: .1rem .3rem; border-radius: 4px; }
@media print { body { max-width: none; margin: 0; } a { color: #000; } }
"""

_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{style}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def render_report_html(markdown_body: str, *, title: str) -> str:
    """Wrap a report's markdown body in a self-contained, styled HTML document.

    ``markdown_body`` is converted with markdown-it (gfm-like, so pipe tables
    render). The fragment is embedded in a full document whose ``<head>``
    carries an HTML-escaped ``<title>`` and an inline ``<style>``. No external
    CSS/JS — the result is a single portable file.
    """
    fragment = _MD.render(markdown_body)
    return _TEMPLATE.format(title=html.escape(title), style=_STYLE, body=fragment)


__all__ = ["render_report_html"]
```

Note: `_TEMPLATE.format(...)` only substitutes the three placeholders in `_TEMPLATE` itself; the CSS braces live inside the `_STYLE` *value* and the markdown HTML inside the `body` *value*, so they are never interpreted as format fields. The `test_markdown_is_converted_including_tables` `<table>` assertion is the gate that the `gfm-like` preset renders tables — if it ever fails, `MarkdownIt("commonmark").enable("table")` is the equivalent fallback.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/core/test_report_html.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/core/report_html.py tests/core/test_report_html.py
uv run ruff format src/newsletter/core/report_html.py tests/core/test_report_html.py
git add src/newsletter/core/report_html.py tests/core/test_report_html.py
git commit -m "feat(core): self-contained HTML renderer for report markdown"
```

---

### Task 2: trends CLI `--format`

**Files:**
- Modify: `src/newsletter/slices/trends/cli.py`
- Test: `tests/slices/trends/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/slices/trends/test_cli.py` (the file already defines `runner`, `_seed_source`, `_seed`):

```python
def test_trends_html_format(db_session):
    _seed_source(db_session)
    _seed(db_session, title="Sora video model", published_at=datetime(2026, 5, 18, 9, 0))
    db_session.commit()
    result = runner.invoke(
        app,
        ["--period", "week", "--end", "2026-05-21", "--min-count", "1", "--format", "html"],
    )
    assert result.exit_code == 0, result.output
    assert result.output.lstrip().startswith("<!DOCTYPE html>")
    assert "트렌드 리포트" in result.output


def test_trends_rejects_bad_format(db_session):
    result = runner.invoke(
        app, ["--period", "week", "--end", "2026-05-21", "--format", "xml"]
    )
    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/slices/trends/test_cli.py -v`
Expected: FAIL — `test_trends_html_format` produces markdown (no `<!DOCTYPE html>`), and `--format` is an unknown option so the bad-format case errors for the wrong reason.

- [ ] **Step 3: Implement the change**

In `src/newsletter/slices/trends/cli.py`, add the import after the existing `from newsletter.slices.trends.service import analyze_trends` line:

```python
from newsletter.core.report_html import render_report_html
```

Add a `fmt` option to the `cmd_trends` callback signature, immediately after the `save` option (keep `save` last is not required; place `fmt` before `save`):

```python
    fmt: str = typer.Option("md", "--format", help="md or html."),
    save: str | None = typer.Option(
        None, "--save", help="Write the report to this path instead of stdout."
    ),
```

After the existing `period` validation block, add format validation:

```python
    if period not in ("week", "month"):
        typer.echo("period must be 'week' or 'month'", err=True)
        raise typer.Exit(code=1)
    if fmt not in ("md", "html"):
        typer.echo("format must be 'md' or 'html'", err=True)
        raise typer.Exit(code=1)
```

Replace the final output block (currently builds `markdown` and writes/echoes it) with:

```python
    markdown = render_markdown(report)
    output = (
        render_report_html(markdown, title=f"트렌드 리포트 — {period}")
        if fmt == "html"
        else markdown
    )
    if save:
        Path(save).write_text(output, encoding="utf-8")
        typer.echo(f"트렌드 리포트 저장: {save}")
    else:
        typer.echo(output)
```

(The empty-window guard `if report.total_current_items == 0 and report.total_previous_items == 0: typer.echo("(no items in window)"); return` stays exactly as-is, before this block.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/slices/trends/test_cli.py -v`
Expected: PASS — including the existing `test_trends_saves_to_file` and `test_trends_reports_new_term` (unchanged because `fmt` defaults to `md`).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/trends/cli.py tests/slices/trends/test_cli.py
uv run ruff format src/newsletter/slices/trends/cli.py tests/slices/trends/test_cli.py
git add src/newsletter/slices/trends/cli.py tests/slices/trends/test_cli.py
git commit -m "feat(trends): --format md|html on the report CLI"
```

---

### Task 3: competitors `report --format`

**Files:**
- Modify: `src/newsletter/slices/competitors/cli.py`
- Test: `tests/slices/competitors/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/slices/competitors/test_cli.py` (the file already defines `runner`, imports `repository`, `CompetitorCreate`, `RawItem`, `ProcessedItem`, `sources_repo`, `SourceCreate`, and `datetime`):

```python
def test_report_html_format(db_session):
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai"]))
    db_session.commit()
    result = runner.invoke(
        app, ["report", "--since", "2026-05-15", "--until", "2026-05-22", "--format", "html"]
    )
    assert result.exit_code == 0, result.output
    assert result.output.lstrip().startswith("<!DOCTYPE html>")
    assert "경쟁사 멘션 리포트" in result.output


def test_report_rejects_bad_format(db_session):
    repository.add(db_session, CompetitorCreate(name="OpenAI", aliases=["openai"]))
    db_session.commit()
    result = runner.invoke(app, ["report", "--format", "pdf"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/slices/competitors/test_cli.py -v`
Expected: FAIL — `--format` is an unknown option / output is markdown not HTML.

- [ ] **Step 3: Implement the change**

In `src/newsletter/slices/competitors/cli.py`, add the import after `from newsletter.slices.competitors.service import analyze_competitors`:

```python
from newsletter.core.report_html import render_report_html
```

Add a `fmt` option to `cmd_report`'s signature, before the existing `save` option:

```python
    fmt: str = typer.Option("md", "--format", help="md or html."),
    save: str | None = typer.Option(
        None, "--save", help="Write the report to this path instead of stdout."
    ),
```

Add format validation as the first statement in the function body (before parsing dates):

```python
    if fmt not in ("md", "html"):
        typer.echo("format must be 'md' or 'html'", err=True)
        raise typer.Exit(code=1)
    since_date = date_cls.fromisoformat(since) if since else None
    until_date = date_cls.fromisoformat(until) if until else None
```

Replace the final output block (currently builds `markdown` and writes/echoes it) with:

```python
    markdown = render_markdown(report)
    output = (
        render_report_html(markdown, title="경쟁사 멘션 리포트")
        if fmt == "html"
        else markdown
    )
    if save:
        Path(save).write_text(output, encoding="utf-8")
        typer.echo(f"경쟁사 리포트 저장: {save}")
    else:
        typer.echo(output)
```

(The `if not repository.list_competitors(session, only_enabled=True): typer.echo("(no competitors registered)"); return` guard inside the `with session_scope()` block stays exactly as-is.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/slices/competitors/test_cli.py -v`
Expected: PASS — including the existing `test_report_save_writes_file` and `test_report_smoke` (unchanged because `fmt` defaults to `md`).

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check --fix src/newsletter/slices/competitors/cli.py tests/slices/competitors/test_cli.py
uv run ruff format src/newsletter/slices/competitors/cli.py tests/slices/competitors/test_cli.py
git add src/newsletter/slices/competitors/cli.py tests/slices/competitors/test_cli.py
git commit -m "feat(competitors): --format md|html on the report CLI"
```

---

### Task 4: AGENTS.md docs + full verification

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Update the two command rows**

Edit `AGENTS.md`. In the `trends` command row, add `[--format md\|html]` before the trailing `[--save PATH]`:

```markdown
| `uv run newsletter trends [--period week\|month] [--end DATE] [--top N] [--min-count N] [--format md\|html] [--save PATH]` | Period-over-period AI topic trend report (rising / cooling / new / gone) |
```

In the `competitors` command row, add `[--format md\|html]` before `[--save PATH]`:

```markdown
| `uv run newsletter competitors add \| list \| remove \| enable \| disable \| report [--days N \| --since DATE] [--until DATE] [--top K] [--format md\|html] [--save PATH]` | Register competitors and report their mentions across collected items |
```

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -q`
Expected: all pass. Prior baseline was 588; this adds ~8 (4 renderer + 2 trends + 2 competitors), so expect ~596 passing, 0 failed.

- [ ] **Step 3: Manual smoke of HTML output**

Run: `uv run newsletter competitors add --name OpenAI --aliases openai && uv run newsletter competitors report --format html`
Expected: prints an HTML document beginning with `<!DOCTYPE html>` and containing `경쟁사 멘션 리포트`. (Then `uv run newsletter competitors remove 1` to clean up the demo row, if desired — note this writes to the configured DB.)

- [ ] **Step 4: Lint check**

Run: `uv run ruff check src/newsletter/core/report_html.py src/newsletter/slices/trends/cli.py src/newsletter/slices/competitors/cli.py tests/core/test_report_html.py tests/slices/trends/test_cli.py tests/slices/competitors/test_cli.py`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md
git commit -m "docs: --format md|html on trends and competitors report commands"
```

---

## Self-Review Notes

- **Spec coverage:** shared renderer in `core` (Task 1); `--format md|html` on trends (Task 2) and competitors (Task 3); self-contained / no external resources (Task 1 test); markdown stays canonical, HTML derived (Tasks 2/3 branch on `fmt`, default `md` → regression 0); bad-format friendly exit (Tasks 2/3); docs (Task 4). All design sections map to a task.
- **Type consistency:** `render_report_html(markdown_body: str, *, title: str) -> str` is defined in Task 1 and called identically in Tasks 2 and 3. The CLI option param is named `fmt` (bound to `--format`) consistently in both CLIs to avoid shadowing the `format` builtin.
- **No placeholders:** every code step shows complete code; every run step has an exact command and expected outcome.
- **markdown-it tables:** the design referenced `commonmark`+linkify, but CommonMark omits tables; the plan uses the `gfm-like` preset so report pipe tables render, gated by the `<table>` test. This is a deliberate refinement of the spec, not a deviation from intent.
</content>
