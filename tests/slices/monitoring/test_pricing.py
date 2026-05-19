"""Pricing helpers (Iteration 10)."""

from __future__ import annotations

import pytest

from newsletter.slices.monitoring.pricing import cost_for


def test_sonnet_cost():
    # 1M in @ $3, 1M out @ $15.
    assert cost_for("claude-sonnet-4-6", 1_000_000, 0) == pytest.approx(3.0)
    assert cost_for("claude-sonnet-4-6", 0, 1_000_000) == pytest.approx(15.0)


def test_opus_cost():
    assert cost_for("claude-opus-4-7", 1_000_000, 0) == pytest.approx(15.0)
    assert cost_for("claude-opus-4-7", 0, 1_000_000) == pytest.approx(75.0)


def test_unknown_model_falls_back_to_sonnet_rates():
    # We don't want crashes for new model ids; sonnet rate is the safe baseline.
    assert cost_for("unknown-model", 1_000_000, 1_000_000) == pytest.approx(3.0 + 15.0)


def test_zero_tokens_zero_cost():
    assert cost_for("claude-opus-4-7", 0, 0) == 0.0
