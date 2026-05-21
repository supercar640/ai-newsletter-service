"""trends.analysis — classify terms into trend buckets."""

from __future__ import annotations

from newsletter.slices.trends.analysis import compare_windows


def _imp(terms):
    return {t: 0.0 for t in terms}


def test_new_terms_appear_with_min_count():
    cur = {"sora": 3}
    prev = {}
    buckets = compare_windows(cur, prev, importance=_imp(cur))
    assert [d.term for d in buckets.new] == ["sora"]
    assert buckets.rising == []


def test_below_min_count_is_excluded():
    cur = {"sora": 1}  # below default min_count=2
    prev = {}
    buckets = compare_windows(cur, prev, importance=_imp(cur))
    assert buckets.new == []


def test_dropped_terms():
    cur = {}
    prev = {"clubhouse": 4}
    buckets = compare_windows(cur, prev, importance={})
    assert [d.term for d in buckets.dropped] == ["clubhouse"]


def test_rising_and_fading():
    cur = {"rag": 8, "nft": 2}
    prev = {"rag": 3, "nft": 6}
    buckets = compare_windows(cur, prev, importance=_imp(cur))
    assert [d.term for d in buckets.rising] == ["rag"]
    assert [d.term for d in buckets.fading] == ["nft"]
    rag = buckets.rising[0]
    assert rag.current == 8 and rag.previous == 3 and rag.delta == 5


def test_top_n_truncation():
    cur = {f"t{i}": 5 for i in range(20)}
    prev = {}
    buckets = compare_windows(cur, prev, importance=_imp(cur), top_n=3)
    assert len(buckets.new) == 3


def test_importance_breaks_ties_in_top_current():
    cur = {"a": 5, "b": 5}
    prev = {}
    buckets = compare_windows(cur, prev, importance={"a": 1.0, "b": 9.0})
    # equal counts -> higher importance first
    assert [d.term for d in buckets.top_current] == ["b", "a"]
