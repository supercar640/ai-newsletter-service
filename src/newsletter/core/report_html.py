"""Render a report's markdown body as a self-contained, styled HTML document.

Reports across the app (trends, competitors, and future digests) produce
markdown as their canonical, testable form. This module wraps that markdown
in a single portable HTML file: markdown-it for the body, an inline
``<style>`` block for presentation, and zero external resources so the file
can be shared, viewed offline, or emailed as-is.

The ``commonmark`` markdown-it preset is used with raw HTML disabled
(``{"html": False}``) and the ``table`` rule enabled, so GFM pipe tables
render as real ``<table>`` elements while untrusted content from external
feeds (e.g. article titles) cannot inject live markup. The rendered body is
wrapped in a ``<main class="report">`` card so the stylesheet can center it.
"""

from __future__ import annotations

import html

from markdown_it import MarkdownIt

_MD = MarkdownIt("commonmark", {"html": False}).enable("table")

# Self-contained presentation: CSS custom properties drive light/dark/print
# variants. No remote assets (no @import, web fonts, <link>, or <script>) so a
# single .html file renders identically offline and in email.
_STYLE = """\
:root {
  color-scheme: light dark;
  --report-bg: #eef2f7;
  --report-surface: #ffffff;
  --report-text: #1f2937;
  --report-muted: #64748b;
  --report-heading: #102033;
  --report-border: #d8e0ea;
  --report-border-strong: #c3cedb;
  --report-accent: #2563eb;
  --report-accent-hover: #1d4ed8;
  --report-table-head: #f1f5f9;
  --report-table-row: #ffffff;
  --report-table-zebra: #f8fafc;
  --report-code-bg: #eef2ff;
  --report-quote-bg: #f8fafc;
  --report-shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
}

* { box-sizing: border-box; }

html {
  background: var(--report-bg);
  color: var(--report-text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Apple SD Gothic Neo", "Malgun Gothic", Arial, sans-serif;
  font-size: 16px;
  line-height: 1.65;
  -webkit-text-size-adjust: 100%;
  text-rendering: optimizeLegibility;
}

body {
  margin: 0;
  padding: 40px 20px;
  background: var(--report-bg);
  color: var(--report-text);
}

.report {
  width: min(100%, 980px);
  margin: 0 auto;
  padding: 44px 52px;
  background: var(--report-surface);
  border: 1px solid var(--report-border);
  border-radius: 16px;
  box-shadow: var(--report-shadow);
}

h1, h2, h3 {
  color: var(--report-heading);
  line-height: 1.3;
  overflow-wrap: break-word;
}

h1 {
  margin: 0 0 28px;
  padding-bottom: 18px;
  border-bottom: 2px solid var(--report-border);
  font-size: 2rem;
  font-weight: 760;
}

h2 {
  margin: 40px 0 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--report-border);
  font-size: 1.45rem;
  font-weight: 720;
}

h3 { margin: 28px 0 12px; font-size: 1.15rem; font-weight: 700; }

p { margin: 0 0 16px; }

a {
  color: var(--report-accent);
  text-decoration: underline;
  text-decoration-thickness: 0.08em;
  text-underline-offset: 0.18em;
}

a:hover, a:focus { color: var(--report-accent-hover); }

ul, ol { margin: 0 0 18px; padding-left: 1.45rem; }
li { margin: 6px 0; }
li > ul, li > ol { margin-top: 6px; margin-bottom: 8px; }

table {
  display: block;
  width: 100%;
  max-width: 100%;
  margin: 24px 0;
  overflow-x: auto;
  border-collapse: collapse;
  border: 1px solid var(--report-border-strong);
  border-radius: 10px;
  background: var(--report-table-row);
}

thead { background: var(--report-table-head); }
tr { border-bottom: 1px solid var(--report-border); }
tbody tr:nth-child(even) { background: var(--report-table-zebra); }
tbody tr:last-child { border-bottom: 0; }

th, td {
  min-width: 120px;
  padding: 11px 14px;
  border-right: 1px solid var(--report-border);
  text-align: left;
  vertical-align: top;
}

th:last-child, td:last-child { border-right: 0; }
th { color: var(--report-heading); font-weight: 700; white-space: nowrap; }
td { color: var(--report-text); }

blockquote {
  margin: 22px 0;
  padding: 14px 18px;
  background: var(--report-quote-bg);
  border-left: 4px solid var(--report-accent);
  color: var(--report-muted);
  border-radius: 0 10px 10px 0;
}

blockquote > :last-child { margin-bottom: 0; }

code {
  padding: 0.14em 0.35em;
  background: var(--report-code-bg);
  border-radius: 5px;
  color: var(--report-heading);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 0.92em;
}

pre {
  margin: 22px 0;
  padding: 16px;
  overflow-x: auto;
  background: #0f172a;
  border-radius: 10px;
  color: #e5e7eb;
}

pre code { padding: 0; background: transparent; color: inherit; }

hr { margin: 34px 0; border: 0; border-top: 1px solid var(--report-border); }
img { max-width: 100%; height: auto; }

@media (max-width: 720px) {
  body { padding: 0; }
  .report {
    width: 100%;
    padding: 26px 18px;
    border-right: 0;
    border-left: 0;
    border-radius: 0;
    box-shadow: none;
  }
  h1 { font-size: 1.65rem; }
  h2 { margin-top: 32px; font-size: 1.28rem; }
  h3 { font-size: 1.08rem; }
  th, td { padding: 10px 12px; }
}

@media (prefers-color-scheme: dark) {
  :root {
    --report-bg: #0f172a;
    --report-surface: #111827;
    --report-text: #dbe4ef;
    --report-muted: #a8b3c5;
    --report-heading: #f8fafc;
    --report-border: #263244;
    --report-border-strong: #344256;
    --report-accent: #8ab4ff;
    --report-accent-hover: #b7cdfd;
    --report-table-head: #1f2937;
    --report-table-row: #111827;
    --report-table-zebra: #172033;
    --report-code-bg: #1e293b;
    --report-quote-bg: #172033;
    --report-shadow: 0 18px 45px rgba(0, 0, 0, 0.35);
  }
  pre { background: #020617; }
}

@media print {
  :root {
    --report-bg: #ffffff;
    --report-surface: #ffffff;
    --report-text: #111827;
    --report-heading: #111827;
    --report-border: #cbd5e1;
    --report-shadow: none;
  }
  body { padding: 0; }
  .report {
    width: 100%;
    max-width: none;
    padding: 0;
    border: 0;
    border-radius: 0;
    box-shadow: none;
  }
  a { color: inherit; text-decoration: underline; }
  table { page-break-inside: avoid; }
}
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
<main class="report">
{body}
</main>
</body>
</html>
"""


def render_report_html(markdown_body: str, *, title: str) -> str:
    """Wrap a report's markdown body in a self-contained, styled HTML document.

    ``markdown_body`` is converted with markdown-it using the ``commonmark``
    preset, raw HTML disabled, and the ``table`` rule enabled (so pipe tables
    render as real ``<table>`` elements). Disabling raw HTML ensures untrusted
    content from external feeds — such as article titles — cannot inject live
    markup. The fragment is placed inside a ``<main class="report">`` card in a
    full document whose ``<head>`` carries an HTML-escaped ``<title>`` and an
    inline ``<style>``. No external CSS/JS — the result is a single portable
    file.
    """
    fragment = _MD.render(markdown_body)
    return _TEMPLATE.format(title=html.escape(title), style=_STYLE, body=fragment)


__all__ = ["render_report_html"]
