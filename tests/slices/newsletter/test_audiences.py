"""Audience profiles for template diversification (Phase 2)."""

from __future__ import annotations

import pytest

from newsletter.slices.newsletter.audiences import (
    AUDIENCES,
    DEFAULT_AUDIENCE,
    AudienceProfile,
    resolve_audience,
)


def test_three_known_audiences():
    assert set(AUDIENCES) == {"general", "executive", "technical"}


def test_default_audience_is_general():
    assert DEFAULT_AUDIENCE == "general"
    assert AUDIENCES["general"].name == "general"


def test_executive_has_smaller_counts_than_general():
    g = AUDIENCES["general"]
    e = AUDIENCES["executive"]
    assert e.expert_count < g.expert_count
    assert e.practical_count <= g.practical_count


def test_technical_has_larger_counts_than_general():
    g = AUDIENCES["general"]
    t = AUDIENCES["technical"]
    assert t.expert_count > g.expert_count
    assert t.practical_count >= g.practical_count


def test_each_profile_has_a_template_path():
    for profile in AUDIENCES.values():
        assert profile.template.endswith(".md.j2")
        assert profile.template.startswith("newsletter")


def test_resolve_audience_known_returns_profile():
    p = resolve_audience("executive")
    assert isinstance(p, AudienceProfile)
    assert p.name == "executive"


def test_resolve_audience_unknown_raises():
    with pytest.raises(ValueError, match="audience"):
        resolve_audience("intern")


def test_resolve_audience_none_returns_default():
    p = resolve_audience(None)
    assert p.name == DEFAULT_AUDIENCE
