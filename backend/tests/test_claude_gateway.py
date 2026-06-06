"""LLM gateway tests: fake provider, error mapping, response normalization.

No network — the Claude client is stubbed by injecting a fake into the gateway.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from anthropic.types import TextBlock

from app.core.exceptions import AppError
from app.services.llm.claude_gateway import ClaudeGateway
from app.services.llm.fake_provider import FakeLLMProvider


class _StubMessages:
    def __init__(self, *, response: object = None, error: Exception | None = None):
        self._response = response
        self._error = error

    async def create(self, **kwargs: object) -> object:
        if self._error is not None:
            raise self._error
        return self._response


class _StubClient:
    def __init__(self, *, response: object = None, error: Exception | None = None):
        self.messages = _StubMessages(response=response, error=error)


def _gateway() -> ClaudeGateway:
    return ClaudeGateway(
        api_key="test-key",
        default_model="claude-opus-4-8",
        max_tokens=256,
        timeout=5.0,
        max_retries=0,
    )


async def test_fake_provider_returns_reply() -> None:
    provider = FakeLLMProvider(reply="hi there")
    result = await provider.generate(
        system="s", messages=[{"role": "user", "content": "q"}]
    )
    assert result.text == "hi there"
    assert result.model == "fake-model"
    assert provider.calls[0]["system"] == "s"


async def test_gateway_unconfigured_raises_503() -> None:
    gateway = ClaudeGateway(
        api_key=None,
        default_model="claude-opus-4-8",
        max_tokens=256,
        timeout=5.0,
        max_retries=0,
    )
    with pytest.raises(AppError) as excinfo:
        await gateway.generate(system="s", messages=[{"role": "user", "content": "q"}])
    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "llm_unavailable"


async def test_gateway_maps_unexpected_error_to_502() -> None:
    gateway = _gateway()
    gateway._client = _StubClient(error=RuntimeError("boom"))  # type: ignore[assignment]
    with pytest.raises(AppError) as excinfo:
        await gateway.generate(system="s", messages=[{"role": "user", "content": "q"}])
    assert excinfo.value.status_code == 502
    assert excinfo.value.code == "llm_error"


async def test_gateway_normalizes_response() -> None:
    response = SimpleNamespace(
        content=[TextBlock(type="text", text="hello", citations=None)],
        usage=SimpleNamespace(input_tokens=12, output_tokens=3),
        model="claude-opus-4-8",
        stop_reason="end_turn",
    )
    gateway = _gateway()
    gateway._client = _StubClient(response=response)  # type: ignore[assignment]

    result = await gateway.generate(
        system="s", messages=[{"role": "user", "content": "q"}]
    )
    assert result.text == "hello"
    assert result.model == "claude-opus-4-8"
    assert result.input_tokens == 12
    assert result.output_tokens == 3
    assert result.stop_reason == "end_turn"
