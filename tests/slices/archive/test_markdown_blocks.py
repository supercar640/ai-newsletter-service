"""markdown → Notion block conversion."""

from __future__ import annotations

from newsletter.slices.archive.markdown_blocks import markdown_to_blocks


def _types(blocks):
    return [b["type"] for b in blocks]


def _text(block):
    rt = block[block["type"]]["rich_text"]
    return "".join(t["text"]["content"] for t in rt)


def test_empty_input_yields_no_blocks():
    assert markdown_to_blocks("") == []
    assert markdown_to_blocks("\n\n\n") == []


def test_plain_paragraphs():
    md = "hello world\nsecond line"
    blocks = markdown_to_blocks(md)
    assert _types(blocks) == ["paragraph", "paragraph"]
    assert _text(blocks[0]) == "hello world"
    assert _text(blocks[1]) == "second line"


def test_h1_h2_h3_become_headings():
    md = "# Title\n## Sub\n### Detail"
    blocks = markdown_to_blocks(md)
    assert _types(blocks) == ["heading_1", "heading_2", "heading_3"]
    assert _text(blocks[0]) == "Title"
    assert _text(blocks[1]) == "Sub"
    assert _text(blocks[2]) == "Detail"


def test_h4_and_deeper_collapse_to_h3():
    md = "#### deep heading"
    blocks = markdown_to_blocks(md)
    assert blocks[0]["type"] == "heading_3"
    assert _text(blocks[0]) == "deep heading"


def test_bullet_list_items():
    md = "- one\n- two\n* three"
    blocks = markdown_to_blocks(md)
    assert _types(blocks) == ["bulleted_list_item"] * 3
    assert [_text(b) for b in blocks] == ["one", "two", "three"]


def test_horizontal_rule_becomes_divider():
    md = "before\n---\nafter"
    blocks = markdown_to_blocks(md)
    assert blocks[1]["type"] == "divider"
    assert blocks[0]["type"] == "paragraph"
    assert blocks[2]["type"] == "paragraph"


def test_blank_lines_dropped():
    md = "first\n\n\nsecond"
    blocks = markdown_to_blocks(md)
    assert _types(blocks) == ["paragraph", "paragraph"]


def test_long_line_split_into_2000_char_chunks():
    long_line = "x" * 2500
    blocks = markdown_to_blocks(long_line)
    assert len(blocks) == 1
    rt = blocks[0]["paragraph"]["rich_text"]
    # Notion limit is 2000 chars per rich_text element.
    assert all(len(t["text"]["content"]) <= 2000 for t in rt)
    assert sum(len(t["text"]["content"]) for t in rt) == 2500


def test_caps_to_100_blocks_per_page():
    """Notion accepts up to 100 children per create-page call."""
    md = "\n".join(f"line {i}" for i in range(200))
    blocks = markdown_to_blocks(md)
    assert len(blocks) <= 100


def test_block_text_caps_dont_split_words_at_arbitrary_points_for_short_lines():
    # Lines well under 2000 chars should stay in one rich_text element.
    line = "x" * 1500
    blocks = markdown_to_blocks(line)
    assert len(blocks[0]["paragraph"]["rich_text"]) == 1
