"""Construct the configured LLM provider (cached singleton)."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.services.llm.base import LLMProvider
from app.services.llm.claude_gateway import ClaudeGateway
from app.services.llm.fake_provider import FakeLLMProvider
from app.services.llm.ollama_gateway import OllamaGateway


@lru_cache
def get_llm_provider() -> LLMProvider:
    """FastAPI dependency provider for the LLM gateway."""
    settings = get_settings()
    provider = settings.llm_provider.lower()
    if provider == "fake":
        return FakeLLMProvider()
    if provider == "ollama":
        return OllamaGateway(
            base_url=settings.ollama_base_url,
            default_model=settings.ollama_model,
            max_tokens=settings.claude_max_tokens,
            timeout=settings.ollama_timeout_seconds,
        )
    return ClaudeGateway(
        api_key=settings.anthropic_api_key,
        default_model=settings.claude_model,
        max_tokens=settings.claude_max_tokens,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
