"""Ollama embedding provider — local, free, offline.

Calls the Ollama daemon's ``/api/embed`` endpoint on the host. This is the
local-first counterpart to ``OpenAIEmbeddingProvider``: same Protocol, no API
key, no network egress, and no per-query cost.

Two things matter for latency, and both are handled here:

* **Async-native.** ``aembed_texts`` uses ``httpx.AsyncClient`` so an embedding
  call yields to the event loop instead of blocking it. The sync methods remain
  for the Protocol (and for the background workers), but the request path uses
  the async one.
* **A persistent client + keep_alive.** The HTTP client is reused across calls
  (no TCP/TLS handshake per turn) and ``keep_alive`` pins the model in VRAM, so
  a query embeds in single-digit milliseconds rather than paying a cold model
  load on every idle gap.

Dimension is validated on first use: a model whose output width does not match
the ``vector(N)`` column would otherwise fail deep inside the insert with an
opaque pgvector error.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 60.0


class OllamaEmbeddingProvider:
    """Embeds text with a locally-running Ollama model."""

    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        dimension: int,
        keep_alive: str = "30m",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model_name = model_name
        self._dimension = dimension
        self._keep_alive = keep_alive
        self._async_client: httpx.AsyncClient | None = None
        self._checked_dimension = False

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _payload(self, texts: list[str]) -> dict:
        return {
            "model": self._model_name,
            "input": list(texts),
            "keep_alive": self._keep_alive,
        }

    def _parse(self, data: dict) -> list[list[float]]:
        """Extract vectors from an Ollama embed response.

        ``/api/embed`` returns ``{"embeddings": [[...], ...]}``. The older
        ``/api/embeddings`` shape (``{"embedding": [...]}``) is accepted too so a
        pinned older daemon still works.
        """
        raw = data.get("embeddings")
        if raw is None:
            single = data.get("embedding")
            raw = [single] if single is not None else []
        vectors = [[float(v) for v in vec] for vec in raw]
        self._verify_dimension(vectors)
        return vectors

    def _verify_dimension(self, vectors: list[list[float]]) -> None:
        """Fail loudly on a model/column width mismatch, once."""
        if self._checked_dimension or not vectors:
            return
        actual = len(vectors[0])
        self._checked_dimension = True
        if actual != self._dimension:
            raise RuntimeError(
                f"Ollama model {self._model_name!r} returns {actual}-dimensional "
                f"vectors but EMBEDDING_DIMENSION is {self._dimension}. Set "
                f"EMBEDDING_DIMENSION={actual} and recreate the database, or "
                f"choose a model that emits {self._dimension} dimensions."
            )

    def _unreachable(self, exc: Exception) -> RuntimeError:
        return RuntimeError(
            f"Ollama embeddings request to {self._base_url} failed: {exc}. "
            f"Is the Ollama daemon running, and has {self._model_name!r} been "
            f"pulled (`ollama pull {self._model_name}`)?"
        )

    # ── Sync (Protocol surface; used by background workers) ──────────────────
    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        try:
            response = httpx.post(
                f"{self._base_url}/api/embed",
                json=self._payload(texts),
                timeout=_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self._unreachable(exc) from exc
        return self._parse(response.json())

    # ── Async (the request path) ─────────────────────────────────────────────
    def _client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self._base_url, timeout=_TIMEOUT_SECONDS
            )
        return self._async_client

    async def aembed_texts(self, texts: list[str]) -> list[list[float]]:
        try:
            response = await self._client().post(
                "/api/embed", json=self._payload(texts)
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self._unreachable(exc) from exc
        return self._parse(response.json())

    async def aembed_text(self, text: str) -> list[float]:
        return (await self.aembed_texts([text]))[0]
