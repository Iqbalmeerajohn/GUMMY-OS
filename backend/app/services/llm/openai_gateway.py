"""OpenAI chat LLM gateway.

Implements the ``LLMProvider`` interface against OpenAI's Chat Completions API.
Uses ``httpx`` (already a core dependency) rather than the ``openai`` SDK, so the
production image stays lean and consistent with the OpenAI embedding provider.

OpenAI takes the system prompt as the first message (role="system"), unlike
Anthropic's separate ``system`` parameter, so ``generate`` prepends it. Provider
errors are normalized to ``AppError`` exactly like the Claude gateway, so the API
never leaks a raw 500.
"""

from __future__ import annotations

import logging

import httpx

from app.core.exceptions import AppError
from app.services.llm.base import LLMResponse

logger = logging.getLogger(__name__)


class OpenAIGateway:
    """LLM provider backed by OpenAI's Chat Completions API."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None,
        default_model: str,
        max_tokens: int,
        timeout: float,
        base_url: str,
    ) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")

    async def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if not self._api_key:
            raise AppError(
                "LLM provider is not configured (missing OPENAI_API_KEY).",
                code="llm_unavailable",
                status_code=503,
            )

        used_model = model or self._default_model
        logger.info("Using provider=%s model=%s", self.name, used_model)

        # OpenAI carries the system prompt as the first chat message.
        chat_messages: list[dict[str, str]] = []
        if system:
            chat_messages.append({"role": "system", "content": system})
        chat_messages.extend(messages)

        payload = {
            "model": used_model,
            "messages": chat_messages,
            "max_tokens": max_tokens or self._max_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AppError(
                "The LLM request timed out.",
                code="llm_timeout",
                status_code=504,
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise AppError(
                    "The LLM provider is rate limited. Try again shortly.",
                    code="llm_rate_limited",
                    status_code=429,
                ) from exc
            logger.warning(
                "OpenAI API error (%s): %s",
                exc.response.status_code,
                exc.response.text[:300],
            )
            raise AppError(
                "The LLM provider returned an error.",
                code="llm_error",
                status_code=502,
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("OpenAI request failed: %s", exc)
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

        data = response.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return LLMResponse(
            text=choice["message"]["content"] or "",
            model=data.get("model", used_model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            stop_reason=choice.get("finish_reason") or "stop",
        )
