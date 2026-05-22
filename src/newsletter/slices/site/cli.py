"""``newsletter site`` — render all reports into a linked static HTML folder."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer

from newsletter.core.db import session_scope
from newsletter.core.report_html import render_report_html
from newsletter.slices.monitoring.recorder import build_embedding_client
from newsletter.slices.site.builder import build_index_markdown, build_site_pages

app = typer.Typer(
    name="site",
    help="Render every report into a linked, self-contained static HTML site.",
    invoke_without_command=True,
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def cmd_site(
    out: str = typer.Option("site_out", "--out", help="Output directory for the HTML site."),
) -> None:
    """Generate index.html + one HTML file per report into the output directory."""
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    with session_scope() as session:
        pages = build_site_pages(session, embed_client=build_embedding_client())

    for page in pages:
        rendered = render_report_html(page.markdown, title=page.title)
        (out_dir / f"{page.slug}.html").write_text(rendered, encoding="utf-8")

    index_md = build_index_markdown(pages, generated_at=datetime.now(UTC))
    index_html = render_report_html(index_md, title="AI 인텔리전스 리포트")
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")

    typer.echo(f"사이트 생성 완료: {out_dir} ({len(pages) + 1} files)")
