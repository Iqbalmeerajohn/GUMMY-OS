"""Construct the configured embedding provider and service (cached singletons)."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.embeddings.huggingface_provider import (
    HuggingFaceEmbeddingProvider,
)


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embeddings_provider.lower() == "fake":
        return FakeEmbeddingProvider(dimension=settings.embedding_dimension)
    return HuggingFaceEmbeddingProvider(
        model_name=settings.embeddings_model,
        dimension=settings.embedding_dimension,
    )


@lru_cache
def get_embedding_service() -> EmbeddingService:
    """FastAPI dependency provider for the embedding service."""
    return EmbeddingService(get_embedding_provider())
