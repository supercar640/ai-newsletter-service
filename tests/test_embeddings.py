"""core/embeddings.py — VoyageEmbeddingClient + disabled fallback."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from newsletter.core.embeddings import (
    DisabledEmbeddingClient,
    EmbeddingError,
    VoyageEmbeddingClient,
    cosine,
    deserialize,
    serialize,
)


@dataclass
class _FakeUsage:
    total_tokens: int


@dataclass
class _FakeResult:
    embeddings: list[list[float]]
    total_tokens: int


class _FakeVoyage:
    """Mirrors the voyageai.Client.embed surface we actually call."""

    def __init__(self, vectors: list[list[float]]) -> None:
        self._vectors = vectors
        self.calls: list[dict] = []

    def embed(self, texts, *, model, input_type=None):
        self.calls.append({"texts": texts, "model": model, "input_type": input_type})
        return _FakeResult(
            embeddings=[list(v) for v in self._vectors[: len(texts)]],
            total_tokens=sum(len(t) for t in texts),
        )


def test_voyage_client_returns_one_vector_per_text():
    fake = _FakeVoyage([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    client = VoyageEmbeddingClient(client=fake, model="voyage-3-lite")
    vectors = client.embed(["hello", "world"])
    assert len(vectors) == 2
    assert vectors[0] == [1.0, 0.0, 0.0]
    assert fake.calls[0]["model"] == "voyage-3-lite"
    assert fake.calls[0]["input_type"] == "document"


def test_voyage_client_empty_input_short_circuits():
    fake = _FakeVoyage([])
    client = VoyageEmbeddingClient(client=fake, model="voyage-3-lite")
    assert client.embed([]) == []
    assert fake.calls == []


def test_voyage_client_wraps_errors():
    class _Raises:
        def embed(self, *a, **kw):
            raise RuntimeError("network")

    client = VoyageEmbeddingClient(client=_Raises(), model="voyage-3-lite")
    with pytest.raises(EmbeddingError):
        client.embed(["x"])


def test_voyage_client_calls_usage_callback():
    fake = _FakeVoyage([[1.0, 0.0]])
    captured = []
    client = VoyageEmbeddingClient(
        client=fake,
        model="voyage-3-lite",
        usage_callback=lambda model, tokens: captured.append((model, tokens)),
    )
    client.embed(["one text"])
    assert captured == [("voyage-3-lite", len("one text"))]


def test_disabled_client_returns_no_vectors():
    client = DisabledEmbeddingClient()
    assert client.embed(["a", "b"]) == []


def test_serialize_roundtrip():
    v = [0.1, -0.2, 0.3, 0.4]
    blob = serialize(v)
    assert isinstance(blob, bytes)
    out = deserialize(blob)
    assert out == pytest.approx(v)


def test_serialize_empty():
    assert serialize([]) == b""
    assert deserialize(b"") == []


def test_cosine_basic():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_zero_vector_returns_zero():
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_handles_unequal_length_by_truncation():
    # Defensive — Voyage embeddings are fixed-dim, but tests should not
    # crash if a mismatched pair shows up.
    assert cosine([1.0, 0.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_real_values():
    a = [0.6, 0.8, 0.0]  # unit vector
    b = [0.0, 1.0, 0.0]
    # cos = (0*0 + 0.8*1 + 0) / (1 * 1) = 0.8
    assert cosine(a, b) == pytest.approx(0.8, abs=1e-9)
    # Sanity: magnitude check
    assert math.isclose(math.sqrt(sum(x * x for x in a)), 1.0, abs_tol=1e-9)
