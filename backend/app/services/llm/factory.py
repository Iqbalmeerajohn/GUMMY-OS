"""Construct the configured LLM provider (cached singleton)."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.services.llm.base import LLMProvider
from app.services.llm.claude_gateway import ClaudeGateway
from app.services.llm.fake_provider import FakeLLMProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    """FastAPI dependency provider for the LLM gateway."""
    settings = get_settings()
    if settings.llm_provider.lower() == "fake":
        return FakeLLMProvider()
    return ClaudeGateway(
        api_key=settings.anthropic_api_key,
        default_model=settings.claude_model,
        max_tokens=settings.claude_max_tokens,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
