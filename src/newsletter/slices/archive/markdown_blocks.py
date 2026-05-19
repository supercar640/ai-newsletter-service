"""Pure-function markdown → Notion block converter.

Lives separately from the HTTP client so we can unit-test the shape
without going near respx or the live API.

Intentionally tiny rule set — covers what the newsletter assembler
actually emits today:

* ``# ## ### ...`` headings (4+ collapse to heading_3)
* ``- `` / ``* `` bullets
* ``---`` horizontal rules → ``divider``
* Anything else → ``paragraph``

No inline parsing (bold, italics, links). Notion pages stay readable
even without it; richer conversion can land later if the operator asks.
"""

from __future__ import annotations

from typing import Any, Final

# Notion limits (https://developers.notion.com/reference/request-limits):
# * rich_text element content: 2000 chars
# * children blocks per create-page request: 100
_RICH_TEXT_CHAR_CAP: Final[int] = 2000
_MAX_BLOCKS_PER_PAGE: Final[int] = 100


def markdown_to_blocks(text: str) -> list[dict[str, Any]]:
    """Convert a markdown blob into a (capped) list of Notion blocks."""
    blocks: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        block = _line_to_block(stripped)
        if block is not None:
            blocks.append(block)
        if len(blocks) >= _MAX_BLOCKS_PER_PAGE:
            break
    return blocks


def _line_to_block(line: str) -> dict[str, Any] | None:
    if line.startswith("# "):
        return _heading(1, line[2:].strip())
    if line.startswith("## "):
        return _heading(2, line[3:].strip())
    if line.startswith("### "):
        return _heading(3, line[4:].strip())
    if line.startswith("#### ") or line.startswith("##### ") or line.startswith("###### "):
        return _heading(3, line.lstrip("#").strip())
    if line in ("---", "***", "___"):
        return {"object": "block", "type": "divider", "divider": {}}
    if line.startswith("- ") or line.startswith("* "):
        return _bulleted(line[2:].strip())
    return _paragraph(line)


def _heading(level: int, content: str) -> dict[str, Any]:
    block_type = f"heading_{level}"
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": _rich_text(content)},
    }


def _paragraph(content: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich_text(content)},
    }


def _bulleted(content: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich_text(content)},
    }


def _rich_text(content: str) -> list[dict[str, Any]]:
    """Wrap content as Notion rich_text, splitting at the 2000-char cap."""
    if not content:
        return [{"type": "text", "text": {"content": ""}}]
    if len(content) <= _RICH_TEXT_CHAR_CAP:
        return [{"type": "text", "text": {"content": content}}]
    parts: list[dict[str, Any]] = []
    for start in range(0, len(content), _RICH_TEXT_CHAR_CAP):
        parts.append(
            {
                "type": "text",
                "text": {"content": content[start : start + _RICH_TEXT_CHAR_CAP]},
            }
        )
    return parts


__all__ = ["markdown_to_blocks"]
