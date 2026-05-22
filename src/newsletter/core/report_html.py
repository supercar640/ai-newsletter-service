"""Render a report's markdown body as a self-contained, styled HTML document.

Reports across the app (trends, competitors, and future digests) produce
markdown as their canonical, testable form. This module wraps that markdown
in a single portable HTML file: markdown-it for the body, an inline
``<style>`` block for presentation, and zero external resources so the file
can be shared, viewed offline, or emailed as-is.

The ``commonmark`` markdown-it preset with the ``table`` extension enabled is
used so the GFM pipe tables that reports emit render as real ``<table>``
elements. (``gfm-like`` was attempted first but requires the optional
``linkify-it-py`` package which is not installed in this project.)
"""

from __future__ import annotations

import html

from markdown_it import MarkdownIt

_MD = MarkdownIt("commonmark").enable("table")

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
