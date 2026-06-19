"""Construct the configured LLM provider (cached singleton).

This is the single place allowed to import a concrete gateway. Every service
receives an ``LLMProvider`` by dependency injection, so provider selection happens
here and nowhere else — there is no hardcoded provider fallback.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import get_settings
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Build the LLM provider selected by ``LLM_PROVIDER`` (cached once)."""
    settings = get_settings()
    provider = settings.llm_provider.lower()
    logger.info("LLM provider selected: %s", settings.llm_provider)

    if provider == "fake":
        from app.services.llm.fake_provider import FakeLLMProvider

        return FakeLLMProvider()

    if provider == "openai":
        from app.services.llm.openai_gateway import OpenAIGateway

        return OpenAIGateway(
            api_key=settings.openai_api_key,
            default_model=settings.openai_chat_model,
            max_tokens=settings.claude_max_tokens,
            timeout=settings.llm_timeout_seconds,
            base_url=settings.openai_base_url,
        )

    if provider == "ollama":
        from app.services.llm.ollama_gateway import OllamaGateway

        return OllamaGateway(
            base_url=settings.ollama_base_url,
            default_model=settings.ollama_model,
            max_tokens=settings.claude_max_tokens,
            timeout=settings.ollama_timeout_seconds,
        )

    if provider in ("claude", "anthropic"):
        from app.services.llm.claude_gateway import ClaudeGateway

        return ClaudeGateway(
            api_key=settings.anthropic_api_key,
            default_model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER {settings.llm_provider!r} "
        "(expected one of: openai, claude/anthropic, ollama, fake)."
    )
