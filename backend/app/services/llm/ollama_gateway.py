"""Ollama (local inference) LLM gateway.

Wraps a locally running Ollama server (https://ollama.com) behind the
``LLMProvider`` interface, so chat turns can run fully offline against models
like ``qwen3:8b`` with no API key and no per-call cost. Selected via
``LLM_PROVIDER=ollama``.

Uses Ollama's non-streaming ``POST /api/chat`` endpoint. Errors are normalized to
``AppError`` so the API never leaks a raw 500 (mirrors ``ClaudeGateway``). The
``system`` prompt is sent as a leading ``system`` message, matching the rest of
the gateway contract. Reasoning models (e.g. qwen3) may wrap chain-of-thought in
``<think>…</think>`` — that block is stripped so callers get a clean reply, with
no change to the conversation API contract.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import AsyncIterator

import httpx

from app.core.exceptions import AppError
from app.observability.langfuse import observe_generation
from app.services.llm.base import LLMResponse

logger = logging.getLogger(__name__)

# Strips reasoning models' chain-of-thought so only the answer is returned.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _clean(text: str) -> str:
    return _THINK_BLOCK.sub("", text).strip()


class OllamaGateway:
    """LLM provider backed by a local Ollama server."""

    name = "ollama"

    def __init__(
        self,
        *,
        base_url: str,
        default_model: str,
        max_tokens: int,
        timeout: float,
        keep_alive: str = "30m",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._max_tokens = max_tokens
        self._timeout = timeout
        # Sent on every request, so the warm window is continuously extended
        # while the user is active. Ollama's 5-minute default means a user who
        # steps away pays a multi-second model reload on their next message.
        self._keep_alive = keep_alive
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        """The shared HTTP client.

        Reused across calls so each turn skips connection setup. Creating a
        client per request also discards the connection pool every time, which
        on the chat path is pure added latency for no benefit.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout, connect=5.0),
            )
        return self._client

    def _payload(
        self,
        chat_messages: list[dict[str, str]],
        model: str,
        num_predict: int,
        *,
        stream: bool,
    ) -> dict:
        return {
            "model": model,
            "messages": chat_messages,
            "stream": stream,
            "keep_alive": self._keep_alive,
            "options": {"num_predict": num_predict},
        }

    @observe_generation
    async def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        chat_messages: list[dict[str, str]] = []
        if system:
            chat_messages.append({"role": "system", "content": system})
        chat_messages.extend(messages)

        model_name = model or self._default_model
        logger.info("Using provider=%s model=%s", self.name, model_name)
        num_predict = max_tokens or self._max_tokens
        payload = self._payload(chat_messages, model_name, num_predict, stream=False)

        # Non-streaming: the whole generation arrives in one body, so self._timeout
        # is effectively the read budget. Keep connect short so a dead server fails
        # fast instead of waiting out the full (large) generation window.
        prompt_chars = sum(len(m.get("content", "")) for m in chat_messages)
        logger.info(
            "ollama generate start: model=%s messages=%d prompt_chars=%d "
            "num_predict=%d timeout=%.0fs",
            model_name,
            len(chat_messages),
            prompt_chars,
            num_predict,
            self._timeout,
        )
        start = time.perf_counter()
        try:
            response = await self._http().post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            logger.warning(
                "ollama timed out after %.1fs (limit %.0fs, prompt_chars=%d, "
                "model=%s)",
                time.perf_counter() - start,
                self._timeout,
                prompt_chars,
                model_name,
            )
            raise AppError(
                "The LLM request timed out.",
                code="llm_timeout",
                status_code=504,
            ) from exc
        except httpx.ConnectError as exc:
            raise AppError(
                f"Cannot reach Ollama at {self._base_url}. Is it running?",
                code="llm_unavailable",
                status_code=503,
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("Ollama API error: %s", exc)
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

        text = _clean((data.get("message") or {}).get("content", ""))
        logger.info(
            "ollama generate done: model=%s elapsed=%.1fs input_tokens=%s "
            "output_tokens=%s done_reason=%s reply_chars=%d",
            data.get("model", model_name),
            time.perf_counter() - start,
            data.get("prompt_eval_count"),
            data.get("eval_count"),
            data.get("done_reason"),
            len(text),
        )
        return LLMResponse(
            text=text,
            model=data.get("model", payload["model"]),
            input_tokens=int(data.get("prompt_eval_count", 0) or 0),
            output_tokens=int(data.get("eval_count", 0) or 0),
            stop_reason=data.get("done_reason") or "stop",
        )

    async def stream(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield reply text deltas from Ollama's streaming chat endpoint.

        Note: chain-of-thought is NOT stripped in streaming mode (tags span
        chunks), so this is intended for non-reasoning models like the default
        qwen2.5:3b. Reasoning models would stream their <think> tokens.
        """
        chat_messages: list[dict[str, str]] = []
        if system:
            chat_messages.append({"role": "system", "content": system})
        chat_messages.extend(messages)

        used_model = model or self._default_model
        logger.info("Using provider=%s model=%s", self.name, used_model)
        payload = self._payload(
            chat_messages,
            used_model,
            max_tokens or self._max_tokens,
            stream=True,
        )
        try:
            async with self._http().stream(
                "POST", "/api/chat", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    chunk = (data.get("message") or {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
        except httpx.ConnectError as exc:
            raise AppError(
                f"Cannot reach Ollama at {self._base_url}. Is it running?",
                code="llm_unavailable",
                status_code=503,
            ) from exc
        except httpx.TimeoutException as exc:
            raise AppError(
                "The LLM request timed out.",
                code="llm_timeout",
                status_code=504,
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("Ollama API error (stream): %s", exc)
            raise AppError(
                "The LLM provider returned an error.",
                code="llm_error",
                status_code=502,
            ) from exc

    async def health(self) -> str:
        """Probe the Ollama server. Returns 'ok' when reachable, else 'unavailable'."""
        try:
            response = await self._http().get("/api/tags")
            response.raise_for_status()
        except Exception:
            return "unavailable"
        return "ok"

    async def warm(self) -> None:
        """Load the default model into memory ahead of the first user message.

        Called at startup. An empty ``messages`` list makes Ollama load the model
        and return immediately without generating, so the first real turn is a
        warm one — this is what removes the multi-second cold-start penalty from
        the user's very first message rather than merely from later ones.
        Best-effort: a failure here must never block boot.
        """
        try:
            await self._http().post(
                "/api/chat",
                json={
                    "model": self._default_model,
                    "messages": [],
                    "stream": False,
                    "keep_alive": self._keep_alive,
                },
            )
            logger.info("ollama model %s warmed", self._default_model)
        except Exception:
            logger.info(
                "ollama warm-up skipped (server not reachable yet); "
                "the first turn will pay the model load"
            )
