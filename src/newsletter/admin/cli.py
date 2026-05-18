"""Admin slice CLI — `newsletter admin serve`."""

from __future__ import annotations

import typer
import uvicorn

app = typer.Typer(
    help="Admin web UI commands.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind."),
    port: int = typer.Option(8000, help="Port to bind."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on file change."),
) -> None:
    """Run the admin web server (uvicorn)."""
    uvicorn.run(
        "newsletter.admin.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )
