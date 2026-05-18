"""Shared Jinja2 templates and static-path constants for the admin slice."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

ADMIN_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = ADMIN_DIR / "templates"
STATIC_DIR = ADMIN_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
