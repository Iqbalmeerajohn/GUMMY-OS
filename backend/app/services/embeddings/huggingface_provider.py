"""Hugging Face (sentence-transformers) embedding provider.

The default model is ``all-MiniLM-L6-v2``: a 384-dim sentence encoder that is
small (~80 MB), fast on CPU, has zero per-call cost, and delivers strong semantic
retrieval quality — an excellent fit for private, budget-sensitive memory recall
that still scales to SaaS (batch on CPU now; swap to a GPU/endpoint or larger
model behind this same interface later).

``sentence-transformers`` (and torch) are an OPTIONAL dependency, imported lazily
on first use, so the core app and test suite stay lightweight.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.constants import DEFAULT_EMBEDDING_MODEL, EMBEDDING_DIMENSION

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class HuggingFaceEmbeddingProvider:
    """Embeds text with a locally-run sentence-transformers model."""

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        dimension: int = EMBEDDING_DIMENSION,
    ) -> None:
        self._model_name = model_name
        self._dimension = dimension
        self._model: SentenceTransformer | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _ensure_model(self) -> SentenceTransformer:
        if self._model is None:
            # Lazy import: only pay the torch import cost when actually embedding.
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        model = self._ensure_model()
        vectors = model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [[float(value) for value in row] for row in vectors]
