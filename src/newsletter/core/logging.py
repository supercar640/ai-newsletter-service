"""Structured logging via structlog.

In production we emit JSON; in development we emit a friendly console
renderer. Configure once at app entry (CLI startup, test fixtures).
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor


def _add_app_name(_logger: Any, _method: str, event_dict: EventDict) -> EventDict:
    event_dict.setdefault("app", "newsletter")
    return event_dict


def configure_logging(*, log_format: str = "console", log_level: str = "INFO") -> None:
    """Configure stdlib logging + structlog. Idempotent."""
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_app_name,
        structlog.processors.StackInfoRenderer(),
    ]

    if log_format == "json":
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
