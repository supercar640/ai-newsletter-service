"""corpus.chunking — pure text splitting + keyword extraction."""

from __future__ import annotations

from newsletter.slices.corpus.chunking import chunk_text, extract_keywords


def test_chunk_splits_on_headings():
    text = "# 제목\n첫 문단입니다.\n\n## 둘째\n둘째 문단."
    chunks = chunk_text(text)
    assert len(chunks) == 2
    assert chunks[0].startswith("# 제목")
    assert chunks[1].startswith("## 둘째")


def test_chunk_packs_paragraphs_under_max():
    text = "문단 하나.\n\n문단 둘.\n\n문단 셋."
    chunks = chunk_text(text, max_chars=1000)
    assert chunks == ["문단 하나.\n\n문단 둘.\n\n문단 셋."]


def test_chunk_hard_splits_oversize_block():
    block = " ".join(["word"] * 500)  # > max_chars
    chunks = chunk_text(block, max_chars=100)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)


def test_chunk_drops_empty_and_whitespace():
    assert chunk_text("\n\n   \n\n") == []


def test_extract_keywords_orders_by_frequency_then_alpha():
    text = "rag rag rag agent agent vector"
    kws = extract_keywords(text, max_keywords=3)
    assert kws == ["rag", "agent", "vector"]


def test_extract_keywords_drops_short_tokens_and_stopwords():
    text = "the a AI 및 모델 모델"
    kws = extract_keywords(text)
    assert "the" not in kws
    assert "및" not in kws
    assert "모델" in kws
    assert "ai" in kws
