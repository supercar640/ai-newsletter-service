"""Dedupe / clustering."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from newsletter.slices.processing.dedupe import DedupeInput, assign_groups


def _item(key: int, *, url: str = "", title: str = "", at: datetime | None = None) -> DedupeInput:
    return DedupeInput(key=key, canonical_url=url, title=title, published_at=at)


def test_each_item_gets_a_group_even_when_singleton() -> None:
    groups = assign_groups(
        [_item(1, url="https://a.example/x"), _item(2, url="https://b.example/y")]
    )
    assert set(groups) == {1, 2}
    assert groups[1] != groups[2]


def test_same_canonical_url_clusters() -> None:
    groups = assign_groups(
        [
            _item(1, url="https://a.example/x"),
            _item(2, url="https://a.example/x"),
            _item(3, url="https://a.example/x"),
        ]
    )
    assert groups[1] == groups[2] == groups[3]


def test_title_similarity_groups_within_window() -> None:
    base = datetime(2025, 5, 12, 9, 0, tzinfo=UTC)
    groups = assign_groups(
        [
            _item(
                1,
                url="https://a.example/x",
                title="OpenAI announces GPT-5 with reasoning improvements",
                at=base,
            ),
            _item(
                2,
                url="",
                title="OpenAI announces GPT-5 with reasoning improvements!",
                at=base + timedelta(hours=2),
            ),
        ]
    )
    assert groups[1] == groups[2]


def test_title_similarity_skipped_outside_window() -> None:
    base = datetime(2025, 5, 12, 9, 0, tzinfo=UTC)
    groups = assign_groups(
        [
            _item(
                1,
                url="https://a.example/x",
                title="OpenAI announces GPT-5",
                at=base,
            ),
            _item(
                2,
                url="",
                title="OpenAI announces GPT-5",
                at=base + timedelta(days=3),
            ),
        ]
    )
    assert groups[1] != groups[2]


def test_dissimilar_titles_get_distinct_groups() -> None:
    groups = assign_groups(
        [
            _item(1, url="", title="OpenAI launches new product"),
            _item(2, url="", title="Tesla earnings beat forecast"),
        ]
    )
    assert groups[1] != groups[2]


def test_empty_input() -> None:
    assert assign_groups([]) == {}
