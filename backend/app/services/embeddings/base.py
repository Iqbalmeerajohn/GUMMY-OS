"""The embedding provider interface.

A provider turns text into a fixed-dimension vector. Implementations are swappable
(local Hugging Face model, deterministic fake, or a hosted API later) behind this
Protocol — the service and repositories never depend on a concrete provider.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Produces normalized embedding vectors for text."""

    @property
    def model_name(self) -> str:
        """Identifier stored alongside each embedding (provenance)."""
        ...

    @property
    def dimension(self) -> int:
        """The length of every vector this provider returns."""
        ...

    def embed_text(self, text: str) -> list[float]:
        """Embed a single string."""
        ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of strings (order-preserving)."""
        ...


@runtime_checkable
class SupportsAsyncEmbedding(Protocol):
    """Optional capability: embed without blocking the event loop.

    ``EmbeddingProvider.embed_text`` is synchronous, so calling it directly from
    async request code stalls the whole event loop for the duration of the HTTP
    round-trip. Providers that can issue a native async request implement this;
    ``EmbeddingService`` prefers it and falls back to a worker thread otherwise.
    Mirrors the ``SupportsStreaming`` seam on the LLM side.
    """

    async def aembed_text(self, text: str) -> list[float]:
        """Embed a single string without blocking the event loop."""
        ...

    async def aembed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of strings without blocking the event loop."""
        ...
