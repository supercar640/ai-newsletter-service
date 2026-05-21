"""trends.terms — per-title distinct terms."""

from __future__ import annotations

from newsletter.slices.trends.terms import title_terms


def test_title_terms_dedupes_within_title():
    # "rag" appears twice -> counted once per title
    assert title_terms("RAG agent RAG pipeline") == {"rag", "agent", "pipeline"}


def test_title_terms_empty_title():
    assert title_terms("") == set()


def test_title_terms_drops_stopwords_and_short():
    assert "the" not in title_terms("The AI model")
    assert "ai" in title_terms("The AI model")
