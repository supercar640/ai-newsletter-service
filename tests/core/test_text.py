"""core.text — shared lowercased word tokenization."""

from __future__ import annotations

from newsletter.core.text import STOPWORDS, tokenize


def test_tokenize_lowercases_and_splits():
    assert tokenize("OpenAI GPT Model") == ["openai", "gpt", "model"]


def test_tokenize_drops_single_char_and_stopwords():
    out = tokenize("the a AI 및 모델 x")
    assert "the" not in out
    assert "및" not in out  # stopword
    assert "x" not in out   # length 1
    assert "ai" in out
    assert "모델" in out


def test_tokenize_keeps_korean_and_digits():
    out = tokenize("GPT5 출시 2026")
    assert "gpt5" in out
    assert "출시" in out
    assert "2026" in out


def test_stopwords_is_frozenset():
    assert isinstance(STOPWORDS, frozenset)
    assert "the" in STOPWORDS
