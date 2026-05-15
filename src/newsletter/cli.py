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
from newsletter.core.config import get_settings  # noqa: E402
from newsletter.core.logging import configure_logging, get_logger  # noqa: E402
from newsletter.slices.sources.cli import app as sources_app  # noqa: E402

app = typer.Typer(
    name="newsletter",
    help="AI Newsletter Service — collect, process, draft, review, send.",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(sources_app, name="sources")


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
