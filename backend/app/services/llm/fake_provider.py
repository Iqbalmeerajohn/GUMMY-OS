"""Deterministic, dependency-free LLM provider for dev and tests.

Returns a canned reply without any network call, and records the calls it
received so tests can assert on the assembled system prompt / messages.
"""

from __future__ import annotations

import logging

from app.services.llm.base import LLMResponse
from app.utils.tokens import estimate_tokens

logger = logging.getLogger(__name__)


class FakeLLMProvider:
    """A stand-in for a real chat model."""

    name = "fake"

    def __init__(self, *, reply: str = "This is a fake assistant reply.") -> None:
        self._reply = reply
        self.calls: list[dict[str, object]] = []

    async def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        used_model = model or "fake-model"
        logger.info("Using provider=%s model=%s", self.name, used_model)
        self.calls.append({"system": system, "messages": messages, "model": model})
        return LLMResponse(
            text=self._reply,
            model=used_model,
            input_tokens=estimate_tokens(system),
            output_tokens=estimate_tokens(self._reply),
            stop_reason="end_turn",
        )
