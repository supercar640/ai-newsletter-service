"""competitors.matching — pure alias matching."""

from __future__ import annotations

from newsletter.slices.competitors.matching import (
    CompetitorProfile,
    alias_matches,
    mentioned_competitor_ids,
)


def test_ascii_alias_matches_on_word_boundary():
    # "meta" must NOT match inside "metadata"
    assert alias_matches("openai released metadata tooling", "meta") is False
    assert alias_matches("meta launched llama 4", "meta") is True


def test_non_ascii_alias_matches_as_substring():
    # Korean particles attach with no boundary, so substring matching is required.
    assert alias_matches("네이버가 하이퍼클로바를 공개했다", "하이퍼클로바") is True
    assert alias_matches("카카오 소식", "하이퍼클로바") is False


def test_matching_is_case_insensitive_for_ascii():
    # text is pre-lowered by the caller; alias is stored lowered too.
    assert alias_matches("openai ships gpt-5", "openai") is True


def test_empty_alias_is_ignored():
    assert alias_matches("anything at all", "") is False


def test_mentioned_competitor_ids_returns_all_matches():
    competitors = [
        CompetitorProfile(id=1, name="OpenAI", aliases=("openai", "gpt")),
        CompetitorProfile(id=2, name="Google", aliases=("gemini", "deepmind")),
        CompetitorProfile(id=3, name="Anthropic", aliases=("claude",)),
    ]
    text = "openai and gemini both shipped models today"
    assert mentioned_competitor_ids(text, competitors) == {1, 2}
