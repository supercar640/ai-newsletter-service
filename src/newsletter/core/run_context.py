"""Per-run output directory bookkeeping.

Each ``newsletter collect`` invocation creates a timestamped run directory
under ``DATA_DIR/runs/`` that holds artifacts: scraped HTML for news,
audio + transcripts for YouTube, raw feed XML, etc. Collectors that
need to write files take a ``RunContext`` and ask for a sub-path via
:meth:`subdir`.

The DB stays the durable index; the run directory is the on-disk
companion for files that don't fit in a column.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from newsletter.core.config import get_settings

_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(value: str) -> str:
    cleaned = _SLUG_RE.sub("-", value.strip())
    return cleaned.strip("-") or "unnamed"


class RunContext:
    """A timestamped output directory for one collection / pipeline run."""

    def __init__(self, root: Path, run_id: str) -> None:
        self.run_id = run_id
        self.root = root.resolve()
        self.path = self.root / "runs" / run_id
        self.path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def new(cls, root: Path | str | None = None, *, run_id: str | None = None) -> RunContext:
        """Create a new run directory under ``root`` (defaults to ``DATA_DIR``)."""
        if root is None:
            root = Path(get_settings().data_dir)
        if isinstance(root, str):
            root = Path(root)
        rid = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        return cls(root, rid)

    def subdir(self, *parts: str) -> Path:
        """Return (creating if absent) a subdirectory under the run path.

        Each part is slugified — Korean characters, spaces, etc. are kept
        only as filesystem-safe ASCII-ish slugs.
        """
        path = self.path
        for part in parts:
            path = path / _slug(part)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return f"RunContext(run_id={self.run_id!r}, path={self.path})"
