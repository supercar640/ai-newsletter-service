"""Newsletter CLI entry point.

This is the Typer root app. Each slice mounts a sub-app under a slice name
(e.g. ``newsletter sources list``). Slice commands are registered lazily
as slices come online — see ``Iteration 1+`` of the implementation plan.
"""

from __future__ import annotations

import typer

from newsletter import __version__
from newsletter.core.config import get_settings
from newsletter.core.logging import configure_logging, get_logger

app = typer.Typer(
    name="newsletter",
    help="AI Newsletter Service — collect, process, draft, review, send.",
    no_args_is_help=True,
    add_completion=False,
)


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
