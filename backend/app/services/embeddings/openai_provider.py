"""OpenAI embedding provider (default in production).

Calls OpenAI's hosted ``/embeddings`` endpoint over HTTP. This deliberately uses
``httpx`` (already a core dependency) rather than the ``openai`` SDK, so the
production image stays lean — no ``torch``/CUDA, no extra heavy packages.

``text-embedding-3-small`` supports the ``dimensions`` request parameter, so we
ask for exactly ``EMBEDDING_DIMENSION`` (384) and the result drops straight into
the existing ``Vector(384)`` pgvector column — no schema migration, no re-shaping.

The provider constructs without the API key (so the app still boots when it is
unset); the key is only required when an embedding is actually requested.
"""

from __future__ import annotations

import httpx

from app.core.constants import (
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
)

_TIMEOUT_SECONDS = 30.0


class OpenAIEmbeddingProvider:
    """Embeds text with OpenAI's hosted embedding API."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model_name: str = DEFAULT_OPENAI_EMBEDDING_MODEL,
        dimension: int = EMBEDDING_DIMENSION,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._dimension = dimension
        self._base_url = base_url.rstrip("/")

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self._api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured but EMBEDDING_PROVIDER=openai. "
                "Set OPENAI_API_KEY, or set EMBEDDING_PROVIDER to 'hf' or 'fake'."
            )
        payload = {
            "model": self._model_name,
            "input": list(texts),
            # Match the pgvector column width; supported by text-embedding-3-*.
            "dimensions": self._dimension,
        }
        try:
            response = httpx.post(
                f"{self._base_url}/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"OpenAI embeddings request failed "
                f"({exc.response.status_code}): {exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"OpenAI embeddings request failed: {exc}") from exc

        data = response.json().get("data", [])
        # Preserve input order (the API returns each item's `index`).
        ordered = sorted(data, key=lambda item: item["index"])
        return [[float(value) for value in item["embedding"]] for item in ordered]
