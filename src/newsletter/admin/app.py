"""FastAPI app factory for the admin slice."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from newsletter.admin.templating import STATIC_DIR


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Newsletter Admin",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    from newsletter.admin.routes.dashboard import router as dashboard_router

    app.include_router(dashboard_router)
    return app
