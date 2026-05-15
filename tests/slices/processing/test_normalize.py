"""Title + URL normalization."""

from __future__ import annotations

import pytest

from newsletter.slices.processing.normalize import canonical_url, normalize_title


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("OpenAI announces GPT-5", "OpenAI announces GPT-5"),
        ("  multiple   spaces  ", "multiple spaces"),
        ("\tcontrol\nchars\r\n", "control chars"),
        ('"quoted entirely"', "quoted entirely"),
        ('"open but not "closed', '"open but not "closed'),
        ("", ""),
        (None, ""),
        ("'single quoted'", "single quoted"),
    ],
)
def test_normalize_title(raw, expected) -> None:
    assert normalize_title(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://example.com/foo?utm_source=x&q=1", "https://example.com/foo?q=1"),
        ("HTTPS://Example.com/Foo?fbclid=abc", "https://example.com/Foo"),
        ("https://www.example.com/foo", "https://example.com/foo"),
        ("https://example.com/foo/", "https://example.com/foo"),
        ("https://example.com/", "https://example.com/"),
        ("https://example.com/foo#bar", "https://example.com/foo"),
        # tracking + non-tracking preserved in encoded form
        (
            "https://example.com/x?utm_campaign=y&q=hello+world&utm_id=1",
            "https://example.com/x?q=hello+world",
        ),
        ("", ""),
        (None, ""),
    ],
)
def test_canonical_url(raw, expected) -> None:
    assert canonical_url(raw) == expected


def test_canonical_url_handles_blank_query_kept() -> None:
    # ?empty= is preserved (blank-value), tracking ones are stripped.
    assert (
        canonical_url("https://example.com/x?empty=&utm_source=y") == "https://example.com/x?empty="
    )
