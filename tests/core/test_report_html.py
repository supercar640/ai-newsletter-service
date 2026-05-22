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
