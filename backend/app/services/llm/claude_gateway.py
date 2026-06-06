"""Claude (Anthropic) LLM gateway.

Wraps the official async Anthropic SDK behind the ``LLMProvider`` interface:
configurable model, client-level timeout + automatic retries (the SDK retries
429/5xx with backoff), and provider errors normalized to ``AppError`` so the API
never leaks a raw 500. The client is created lazily and reused.
"""

from __future__ import annotations

import logging
from typing import cast

import anthropic
from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, TextBlock

from app.core.exceptions import AppError
from app.services.llm.base import LLMResponse

logger = logging.getLogger(__name__)


class ClaudeGateway:
    """LLM provider backed by Anthropic's Claude models."""

    name = "claude"

    def __init__(
        self,
        *,
        api_key: str | None,
        default_model: str,
        max_tokens: int,
        timeout: float,
        max_retries: int,
    ) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._max_retries = max_retries
        self._client: AsyncAnthropic | None = None

    def _get_client(self) -> AsyncAnthropic:
        if not self._api_key:
            raise AppError(
                "LLM provider is not configured (missing ANTHROPIC_API_KEY).",
                code="llm_unavailable",
                status_code=503,
            )
        if self._client is None:
            self._client = AsyncAnthropic(
                api_key=self._api_key,
                timeout=self._timeout,
                max_retries=self._max_retries,
            )
        return self._client

    async def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        client = self._get_client()
        try:
            response = await client.messages.create(
                model=model or self._default_model,
                max_tokens=max_tokens or self._max_tokens,
                system=system,
                messages=cast(list[MessageParam], messages),
            )
        except anthropic.APITimeoutError as exc:
            raise AppError(
                "The LLM request timed out.",
                code="llm_timeout",
                status_code=504,
            ) from exc
        except anthropic.RateLimitError as exc:
            raise AppError(
                "The LLM provider is rate limited. Try again shortly.",
                code="llm_rate_limited",
                status_code=429,
            ) from exc
        except anthropic.APIError as exc:
            logger.warning("Claude API error: %s", exc)
            raise AppError(
                "The LLM provider returned an error.",
                code="llm_error",
                status_code=502,
            ) from exc
        except Exception as exc:
            logger.exception("unexpected LLM error")
            raise AppError(
                "An unexpected LLM error occurred.",
                code="llm_error",
                status_code=502,
            ) from exc

        text = "".join(
            block.text for block in response.content if isinstance(block, TextBlock)
        )
        return LLMResponse(
            text=text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason or "end_turn",
        )
