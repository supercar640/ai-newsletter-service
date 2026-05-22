"""Newsletter CLI entry point.

This is the Typer root app. Each slice mounts a sub-app under a slice name
(e.g. ``newsletter sources list``). Slice commands are registered lazily
as slices come online — see ``Iteration 1+`` of the implementation plan.
"""

from __future__ import annotations

import contextlib
import sys

# Force UTF-8 on stdout/stderr before anything writes (Windows defaults to
# cp949 which chokes on Korean text and em-dashes in source names).
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if callable(_reconfigure):
        with contextlib.suppress(OSError, ValueError):
            _reconfigure(encoding="utf-8", errors="replace")

import typer  # noqa: E402 — must follow stdout reconfigure

from newsletter import __version__  # noqa: E402
from newsletter.admin.cli import app as admin_app  # noqa: E402
from newsletter.core.config import get_settings  # noqa: E402
from newsletter.core.logging import configure_logging, get_logger  # noqa: E402
from newsletter.slices.archive.cli import app as archive_app  # noqa: E402
from newsletter.slices.collection.cli import app as collect_app  # noqa: E402
from newsletter.slices.competitors.cli import app as competitors_app  # noqa: E402
from newsletter.slices.corpus.cli import app as corpus_app  # noqa: E402
from newsletter.slices.dashboard.cli import app as dashboard_app  # noqa: E402
from newsletter.slices.departments.cli import app as departments_app  # noqa: E402
from newsletter.slices.distribution.cli import app as send_app  # noqa: E402
from newsletter.slices.distribution.cli import slack_app  # noqa: E402
from newsletter.slices.integration.cli import app as integrate_app  # noqa: E402
from newsletter.slices.interests.cli import app as interests_app  # noqa: E402
from newsletter.slices.monitoring.cli import app as stats_app  # noqa: E402
from newsletter.slices.monthly.cli import app as monthly_app  # noqa: E402
from newsletter.slices.newsletter.cli import app as newsletter_app  # noqa: E402
from newsletter.slices.processing.cli import app as process_app  # noqa: E402
from newsletter.slices.run.cli import app as run_app  # noqa: E402
from newsletter.slices.sources.cli import app as sources_app  # noqa: E402
from newsletter.slices.trends.cli import app as trends_app  # noqa: E402

app = typer.Typer(
    name="newsletter",
    help="AI Newsletter Service — collect, process, draft, review, send.",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(sources_app, name="sources")
app.add_typer(corpus_app, name="corpus")
app.add_typer(dashboard_app, name="dashboard")
app.add_typer(competitors_app, name="competitors")
app.add_typer(interests_app, name="interests")
app.add_typer(departments_app, name="departments")
app.add_typer(collect_app, name="collect")
app.add_typer(process_app, name="process")
app.add_typer(integrate_app, name="integrate")
app.add_typer(newsletter_app, name="newsletter")
app.add_typer(send_app, name="send")
app.add_typer(slack_app, name="slack")
app.add_typer(archive_app, name="archive")
app.add_typer(admin_app, name="admin")
app.add_typer(stats_app, name="stats")
app.add_typer(monthly_app, name="monthly")
app.add_typer(trends_app, name="trends")
app.add_typer(run_app, name="run")


@app.callback()
def _root(
    log_format: str | None = typer.Option(
        None, "--log-format", help="Override LOG_FORMAT (json|console)."
    ),
    log_level: str | None = typer.Option(
        None, "--log-level", help="Override LOG_LEVEL (DEBUG|INFO|WARNING|ERROR)."
    ),
) -> None:
    """Configure logging before any sub-command runs."""
    settings = get_settings()
    configure_logging(
        log_format=log_format or settings.log_format,
        log_level=log_level or settings.log_level,
    )


@app.command()
def version() -> None:
    """Print version and exit."""
    typer.echo(f"newsletter {__version__}")


@app.command()
def hello(name: str = "master") -> None:
    """Sanity check that the CLI is wired up."""
    log = get_logger(__name__)
    log.info("hello", who=name)
    typer.echo(f"Hello, {name}.")


if __name__ == "__main__":  # pragma: no cover
    app()
