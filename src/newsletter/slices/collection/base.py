"""Collector protocol + shared result schema."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from newsletter.models.source import Source


class CollectorResult(BaseModel):
    """One item as returned by a collector, before persistence."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str
    url: str
    published_at: datetime | None = None
    author: str | None = None
    raw_summary: str | None = None
    raw_content: str | None = None
    language: str | None = None


@runtime_checkable
class Collector(Protocol):
    """A collector turns a :class:`Source` into a list of raw items."""

    def collect(self, source: Source) -> list[CollectorResult]: ...


class CollectorError(Exception):
    """Raised when a collector cannot fetch or parse a source."""


class UnsupportedSourceTypeError(Exception):
    """No collector is registered for the given source type."""
