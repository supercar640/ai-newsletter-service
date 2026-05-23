"""Single chokepoint for embedding calls — Voyage today, others later.

All slices route through :class:`EmbeddingClient` so we can:

- centralize the model name + provider switch
- record token usage in RunLog (parallel to ``core/llm.py``)
- short-circuit gracefully when no API key is configured (returns ``[]``
  so callers fall back to lexical clustering instead of crashing)

The MVP stores embeddings on ``ProcessedItem`` as a packed float32 BLOB.
At expected volume (hundreds of items/day, 1024 dims per item ≈ 4 KB)
SQLite handles this without a vector extension.
"""

from __future__ import annotations

import contextlib
import math
import struct
from collections.abc import Callable, Sequence
from typing import Protocol


class EmbeddingError(Exception):
    """Raised when a provider call fails."""


UsageCallback = Callable[[str, int], None]
"""(model_name, total_tokens) → None."""


class EmbeddingClient(Protocol):
    """Provider-agnostic interface."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class DisabledEmbeddingClient:
    """No-op client used when no provider is configured.

    Returns an empty list so consumers can detect "no embeddings available"
    without raising. Used in tests and when ``VOYAGE_API_KEY`` is empty.
    """

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return []


class VoyageEmbeddingClient:
    """Voyage AI implementation.

    The real :class:`voyageai.Client` is constructed lazily (and only when
    no override is passed in) so tests can run without the dependency.
    ``input_type='document'`` is the Voyage hint for stored corpus
    embeddings — short-form titles + summaries fit that mode.
    """

    def __init__(
        self,
        *,
        client: object | None = None,
        model: str = "voyage-3-lite",
        usage_callback: UsageCallback | None = None,
    ) -> None:
        if client is not None:
            self._client = client
        else:  # pragma: no cover - exercised via integration only
            import voyageai

            self._client = voyageai.Client()
        self._model = model
        self._usage_callback = usage_callback

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            result = self._client.embed(list(texts), model=self._model, input_type="document")
        except Exception as exc:
            raise EmbeddingError(f"Voyage embed failed: {exc}") from exc

        tokens = int(getattr(result, "total_tokens", 0) or 0)
        if self._usage_callback is not None:
            with contextlib.suppress(Exception):
                self._usage_callback(self._model, tokens)

        vectors = list(result.embeddings)
        return [list(v) for v in vectors]


def serialize(vector: Sequence[float]) -> bytes:
    """Pack a float vector as little-endian 32-bit floats."""
    if not vector:
        return b""
    return struct.pack(f"<{len(vector)}f", *vector)


def deserialize(blob: bytes | None) -> list[float]:
    """Unpack a BLOB written by :func:`serialize`."""
    if not blob:
        return []
    count = len(blob) // 4
    return list(struct.unpack(f"<{count}f", blob))


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity. Zero magnitude on either side → 0."""
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for i in range(n):
        ai = a[i]
        bi = b[i]
        dot += ai * bi
        norm_a += ai * ai
        norm_b += bi * bi
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


__all__ = [
    "DisabledEmbeddingClient",
    "EmbeddingClient",
    "EmbeddingError",
    "VoyageEmbeddingClient",
    "cosine",
    "deserialize",
    "serialize",
]
