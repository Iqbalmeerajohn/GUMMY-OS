"""Deterministic, dependency-free embedding provider for dev and tests.

Vectors are derived from a hash of the text, so identical text always yields the
identical (unit-normalized) vector — enough to exercise dedupe, storage, and
exact-match ranking without downloading a model. ``call_count`` lets tests assert
that caching/dedupe avoided a recompute.
"""

from __future__ import annotations

import hashlib
import math
import random

from app.core.constants import EMBEDDING_DIMENSION


class FakeEmbeddingProvider:
    """A reproducible stand-in for a real embedding model."""

    def __init__(
        self,
        *,
        dimension: int = EMBEDDING_DIMENSION,
        model_name: str = "fake-deterministic-v1",
    ) -> None:
        self._dimension = dimension
        self._model_name = model_name
        self.call_count = 0

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> list[float]:
        self.call_count += 1
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(seed)
        vector = [rng.gauss(0.0, 1.0) for _ in range(self._dimension)]
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]
