"""Langfuse observability: disabled-by-default, cost model, tracing wrappers.

No network and no real Langfuse client — the enabled path injects a fake client
so we can assert what gets recorded (usage, cost, latency) without leaving the
process. The SDK is never imported here; tracing stays a pure pass-through when
disabled, which is the only state CI ever runs in.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.observability import langfuse as lf
from app.services.llm.base import LLMResponse


@pytest.fixture(autouse=True)
def _reset_langfuse() -> Any:
    """Each test starts and ends with tracing disabled (clean module state)."""
    lf.reset_for_tests()
    yield
    lf.reset_for_tests()


def _settings(*, enabled: bool) -> SimpleNamespace:
    """A minimal settings stand-in (avoids coupling to the dev .env file)."""
    return SimpleNamespace(
        langfuse_enabled=enabled,
        langfuse_public_key="pk" if enabled else None,
        langfuse_secret_key="sk" if enabled else None,
        langfuse_host="https://cloud.langfuse.com",
        langfuse_environment=None,
        langfuse_sample_rate=1.0,
        app_env="test",
        version="0.1.0",
    )


# ── Cost model ────────────────────────────────────────────────────────────────


def test_cost_known_model() -> None:
    cost = lf.estimate_cost_usd("claude-opus-4-8", 1_000_000, 1_000_000)
    assert cost == {"input": 15.0, "output": 75.0, "total": 90.0}


def test_cost_prefix_match() -> None:
    # gpt-4o-mini must win over the shorter gpt-4o prefix (longest/explicit key).
    cost = lf.estimate_cost_usd("gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost == {"input": 0.15, "output": 0.60, "total": 0.75}


def test_cost_unknown_model_returns_none() -> None:
    assert lf.estimate_cost_usd("qwen2.5:3b", 100, 100) is None
    assert lf.estimate_cost_usd(None, 100, 100) is None


# ── Disabled (no keys) — everything is a no-op pass-through ────────────────────


def test_init_disabled_without_keys() -> None:
    assert lf.init_langfuse(_settings(enabled=False)) is False
    assert lf.is_enabled() is False


def test_context_managers_noop_when_disabled() -> None:
    with lf.observe_retrieval(input="q") as span:
        span.update(output={"returned": 0})  # must not raise
    with lf.observe_agent_run("orchestrate") as span:
        span.update(metadata={"k": "v"})  # must not raise


async def test_generation_decorator_passthrough_when_disabled() -> None:
    calls: list[dict[str, Any]] = []

    @lf.observe_generation
    async def generate(
        self: Any, *, system: str, messages: list[dict]
    ) -> LLMResponse:
        calls.append({"system": system})
        return LLMResponse(
            text="hi", model="claude-opus-4-8", input_tokens=5,
            output_tokens=2, stop_reason="end_turn",
        )

    gateway = SimpleNamespace(name="claude")
    result = await generate(
        gateway, system="s", messages=[{"role": "user", "content": "q"}]
    )
    assert result.text == "hi"
    assert calls == [{"system": "s"}]


# ── Enabled — a fake client records what we send ───────────────────────────────


class _FakeObservation:
    def __init__(self, sink: dict[str, Any]) -> None:
        self._sink = sink

    def update(self, **fields: Any) -> _FakeObservation:
        self._sink.setdefault("updates", []).append(fields)
        return self

    def end(self) -> _FakeObservation:
        self._sink["ended"] = True
        return self


class _FakeCurrentObs:
    def __init__(self, sink: dict[str, Any]) -> None:
        self._obs = _FakeObservation(sink)

    def __enter__(self) -> _FakeObservation:
        return self._obs

    def __exit__(self, *exc: Any) -> bool:
        return False


class _FakeClient:
    def __init__(self) -> None:
        self.generations: list[dict[str, Any]] = []
        self.spans: list[dict[str, Any]] = []
        self.flushed = False
        self.shut = False

    def start_observation(
        self, *, as_type: str, name: str, **kw: Any
    ) -> _FakeObservation:
        sink: dict[str, Any] = {"as_type": as_type, "name": name, "start": kw}
        self.generations.append(sink)
        return _FakeObservation(sink)

    def start_as_current_observation(
        self, *, as_type: str, name: str, **kw: Any
    ) -> _FakeCurrentObs:
        sink: dict[str, Any] = {"as_type": as_type, "name": name, "start": kw}
        self.spans.append(sink)
        return _FakeCurrentObs(sink)

    def flush(self) -> None:
        self.flushed = True

    def shutdown(self) -> None:
        self.shut = True


def _enable(fake: _FakeClient) -> None:
    lf._client = fake  # type: ignore[assignment]
    lf._initialized = True


async def test_generation_decorator_records_usage_and_cost() -> None:
    fake = _FakeClient()
    _enable(fake)

    @lf.observe_generation
    async def generate(
        self: Any, *, system: str, messages: list[dict]
    ) -> LLMResponse:
        return LLMResponse(
            text="answer", model="claude-opus-4-8", input_tokens=1_000_000,
            output_tokens=1_000_000, stop_reason="end_turn",
        )

    gateway = SimpleNamespace(name="claude")
    result = await generate(
        gateway, system="s", messages=[{"role": "user", "content": "q"}]
    )

    assert result.text == "answer"
    assert len(fake.generations) == 1
    gen = fake.generations[0]
    assert gen["as_type"] == "generation"
    assert gen["name"] == "claude.generate"
    assert gen["ended"] is True
    final = gen["updates"][-1]
    assert final["usage_details"] == {
        "input": 1_000_000,
        "output": 1_000_000,
        "total": 2_000_000,
    }
    assert final["cost_details"] == {"input": 15.0, "output": 75.0, "total": 90.0}
    assert final["output"] == "answer"


async def test_generation_decorator_records_error() -> None:
    fake = _FakeClient()
    _enable(fake)

    @lf.observe_generation
    async def generate(
        self: Any, *, system: str, messages: list[dict]
    ) -> LLMResponse:
        raise RuntimeError("boom")

    gateway = SimpleNamespace(name="openai")
    with pytest.raises(RuntimeError, match="boom"):
        await generate(gateway, system="s", messages=[])

    gen = fake.generations[0]
    assert gen["ended"] is True
    assert gen["updates"][-1]["level"] == "ERROR"


def test_retrieval_span_records_output_when_enabled() -> None:
    fake = _FakeClient()
    _enable(fake)
    with lf.observe_retrieval(input="who am I") as span:
        span.update(output={"returned": 3, "top_score": 0.9})
    span_sink = fake.spans[0]
    assert span_sink["as_type"] == "retriever"
    assert span_sink["updates"][-1]["output"]["returned"] == 3


def test_agent_span_records_error_level_on_exception() -> None:
    fake = _FakeClient()
    _enable(fake)
    with pytest.raises(ValueError, match="bad"), lf.observe_agent_run("orchestrate"):
        raise ValueError("bad")
    span_sink = fake.spans[0]
    assert span_sink["as_type"] == "agent"
    assert any(u.get("level") == "ERROR" for u in span_sink.get("updates", []))


def test_flush_and_shutdown_when_enabled() -> None:
    fake = _FakeClient()
    _enable(fake)
    lf.flush()
    assert fake.flushed is True
    lf.shutdown()
    assert fake.shut is True
    assert lf.is_enabled() is False
