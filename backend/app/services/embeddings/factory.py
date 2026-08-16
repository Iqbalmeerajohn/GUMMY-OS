"""Construct the configured embedding provider and service (cached singletons)."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.embeddings.ollama_provider import OllamaEmbeddingProvider
from app.services.embeddings.openai_provider import OpenAIEmbeddingProvider


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    provider = settings.embeddings_provider.lower()

    if provider == "fake":
        return FakeEmbeddingProvider(dimension=settings.embedding_dimension)

    if provider == "openai":
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model_name=settings.openai_embeddings_model,
            dimension=settings.embedding_dimension,
            base_url=settings.openai_base_url,
        )

    if provider == "ollama":
        return OllamaEmbeddingProvider(
            base_url=settings.ollama_base_url,
            model_name=settings.ollama_embedding_model,
            dimension=settings.embedding_dimension,
            keep_alive=settings.ollama_keep_alive,
        )

    if provider in ("hf", "huggingface"):
        # Import here ONLY for the HF provider so sentence-transformers/torch is
        # never imported (and need not even be installed) for openai/fake.
        from app.services.embeddings.huggingface_provider import (
            HuggingFaceEmbeddingProvider,
        )

        return HuggingFaceEmbeddingProvider(
            model_name=settings.embeddings_model,
            dimension=settings.embedding_dimension,
        )

    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER {settings.embeddings_provider!r} "
        "(expected one of: ollama, openai, hf, fake)."
    )


@lru_cache
def get_embedding_service() -> EmbeddingService:
    """FastAPI dependency provider for the embedding service."""
    return EmbeddingService(get_embedding_provider())
