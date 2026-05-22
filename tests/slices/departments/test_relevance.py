"""departments.relevance — pure scoring helpers."""

from __future__ import annotations

from newsletter.slices.departments.relevance import (
    department_tokens,
    embedding_score,
    keyword_score,
)


def test_department_tokens_drops_short_and_stopwords():
    toks = department_tokens("영업", "고객 매출 the a")
    assert "영업" in toks
    assert "고객" in toks
    assert "매출" in toks
    assert "the" not in toks  # stopword
    assert "a" not in toks  # length-1


def test_keyword_score_counts_overlap():
    dept = department_tokens("영업", "고객 매출 영업")
    assert keyword_score(dept, "신규 고객 매출 분석 발표") == 2  # 고객, 매출
    assert keyword_score(dept, "엔지니어링 코드 리뷰") == 0


def test_embedding_score_cosine_and_empty():
    assert embedding_score([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert embedding_score([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert embedding_score([], [1.0, 0.0]) == 0.0
    assert embedding_score([1.0, 0.0], []) == 0.0
