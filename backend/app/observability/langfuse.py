"""Langfuse observability — LLM/agent tracing, token & cost accounting.

Every LLM call, memory retrieval, and agent orchestration can be traced to
Langfuse so latency, token usage, and cost are observable in production. The
integration is built on three principles, mirroring the Sentry module
(``app.core.observability``):

* **Disabled by default.** Tracing is a no-op until BOTH ``LANGFUSE_PUBLIC_KEY``
  and ``LANGFUSE_SECRET_KEY`` are configured, so local and CI runs never emit
  events and never need the SDK installed.
* **No secrets in the repo.** Keys come from the environment only.
* **Best-effort.** Every public entrypoint is wrapped so an observability fault
  (bad keys, SDK missing, network blip) can never propagate into a user request
  or a background worker. A trace is never worth a failed turn.

The Langfuse SDK (v4, OpenTelemetry-based) is imported lazily inside
:func:`init_langfuse`; nested observations attach to the current span via OTEL
context, so an LLM ``generation`` created inside :func:`observe_agent_run`
becomes a child of that agent span automatically — including across the
parallel ``asyncio.gather`` fan-out (contextvars are copied per task).
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Awaitable, Callable, Coroutine, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langfuse import Langfuse

    from app.core.config import Settings
    from app.services.llm.base import LLMResponse

logger = logging.getLogger(__name__)

# Module-global client. ``None`` means tracing is disabled — every wrapper below
# short-circuits to a pass-through in that state.
_client: Langfuse | None = None
_initialized = False

# ── Cost model ────────────────────────────────────────────────────────────────
# List price in USD per 1,000,000 tokens, as (input, output), keyed by a model-id
# prefix (longest match wins). Langfuse also infers cost from its own server-side
# model table, but we compute it client-side too so newer model ids (e.g.
# ``claude-opus-4-8``) are always costed even if Langfuse hasn't catalogued them.
# Keep these in sync with the providers' public pricing pages.
_MODEL_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4": (1.0, 5.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.0),
}
_USD_PER_MTOK = 1_000_000.0


def estimate_cost_usd(
    model: str | None, input_tokens: int, output_tokens: int
) -> dict[str, float] | None:
    """Return Langfuse ``cost_details`` for a call, or ``None`` if model unknown.

    Local-inference models (Ollama) and any model absent from the pricing table
    return ``None`` — callers then let Langfuse infer cost (or record none).
    """
    if not model:
        return None
    pricing = next(
        (
            rate
            for prefix, rate in _MODEL_PRICING_PER_MTOK.items()
            if model.startswith(prefix)
        ),
        None,
    )
    if pricing is None:
        return None
    input_rate, output_rate = pricing
    input_cost = input_tokens * input_rate / _USD_PER_MTOK
    output_cost = output_tokens * output_rate / _USD_PER_MTOK
    return {
        "input": input_cost,
        "output": output_cost,
        "total": input_cost + output_cost,
    }


# ── Lifecycle ─────────────────────────────────────────────────────────────────


def init_langfuse(settings: Settings) -> bool:
    """Initialize the Langfuse client once. Returns True when tracing is active.

    No-op (returns False) when either key is missing. Any initialization error —
    including the SDK not being installed — is logged and swallowed so the app
    boots regardless.
    """
    global _client, _initialized
    if _initialized:
        return _client is not None
    _initialized = True

    if not settings.langfuse_enabled:
        logger.info("Langfuse disabled (LANGFUSE_PUBLIC_KEY/SECRET_KEY not set)")
        return False

    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            environment=settings.langfuse_environment or settings.app_env,
            release=settings.version,
            sample_rate=settings.langfuse_sample_rate,
        )
        logger.info(
            "Langfuse initialized (host=%s, env=%s, sample_rate=%.2f)",
            settings.langfuse_host,
            settings.langfuse_environment or settings.app_env,
            settings.langfuse_sample_rate,
        )
        return True
    except Exception:  # pragma: no cover - defensive
        logger.exception("Langfuse init failed; continuing without LLM tracing")
        _client = None
        return False


def is_enabled() -> bool:
    """True when a Langfuse client is active and tracing should be emitted."""
    return _client is not None


def flush() -> None:
    """Flush buffered events (best-effort). Safe to call when disabled."""
    if _client is None:
        return
    try:
        _client.flush()
    except Exception:  # pragma: no cover - defensive
        logger.debug("Langfuse flush failed", exc_info=True)


def shutdown() -> None:
    """Flush and tear down the client on app shutdown (best-effort)."""
    global _client, _initialized
    if _client is not None:
        try:
            _client.shutdown()
        except Exception:  # pragma: no cover - defensive
            logger.debug("Langfuse shutdown failed", exc_info=True)
    _client = None
    _initialized = False


def reset_for_tests() -> None:
    """Reset module state so a test can re-run :func:`init_langfuse`."""
    global _client, _initialized
    _client = None
    _initialized = False


# ── Span handle ───────────────────────────────────────────────────────────────


class _Span:
    """Thin best-effort wrapper around a Langfuse observation (or a no-op).

    Yielded by :func:`observe_retrieval` / :func:`observe_agent_run`. ``update``
    forwards trace fields to the underlying observation, swallowing any fault —
    instrumentation must never break the traced operation.
    """

    __slots__ = ("_obs",)

    def __init__(self, obs: Any | None) -> None:
        self._obs = obs

    def update(self, **fields: Any) -> None:
        if self._obs is None:
            return
        try:
            self._obs.update(**fields)
        except Exception:  # pragma: no cover - defensive
            logger.debug("Langfuse span update failed", exc_info=True)


# ── Context managers for retrieval & agent execution ──────────────────────────


@contextmanager
def _observe(as_type: str, name: str, **start_kwargs: Any) -> Iterator[_Span]:
    """Open an observation of ``as_type`` as the current span, ending on exit.

    The observation becomes the current OTEL span for its ``with`` body, so any
    LLM ``generation`` created inside (e.g. by the gateway decorator) nests
    underneath it. Disabled / faulting → a no-op :class:`_Span`.
    """
    if _client is None:
        yield _Span(None)
        return

    cm = None
    obs = None
    try:
        cm = _client.start_as_current_observation(
            as_type=as_type,  # type: ignore[call-overload]  # as_type is dynamic
            name=name,
            **start_kwargs,
        )
        obs = cm.__enter__()
    except Exception:  # pragma: no cover - defensive
        logger.debug("Langfuse start observation failed", exc_info=True)
        yield _Span(None)
        return

    span = _Span(obs)
    try:
        yield span
    except Exception as exc:
        span.update(level="ERROR", status_message=str(exc)[:500])
        _exit_cm(cm, exc)
        raise
    else:
        _exit_cm(cm, None)


def _exit_cm(cm: Any, exc: BaseException | None) -> None:
    """Close a Langfuse context manager, swallowing instrumentation faults."""
    try:
        if exc is None:
            cm.__exit__(None, None, None)
        else:
            cm.__exit__(type(exc), exc, exc.__traceback__)
    except Exception:  # pragma: no cover - defensive
        logger.debug("Langfuse observation exit failed", exc_info=True)


def observe_retrieval(
    name: str = "memory.retrieve",
    *,
    input: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    """Trace a memory-retrieval operation as a Langfuse ``retriever`` span.

    Returns a context manager yielding a :class:`_Span`; call ``update`` on it to
    record output and metadata (candidate/result counts, top score, latency).
    """
    return _observe("retriever", name, input=input, metadata=metadata)


def observe_agent_run(
    name: str,
    *,
    input: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    """Trace an agent orchestration as a Langfuse ``agent`` span.

    Nested LLM generations attach as children automatically. Returns a context
    manager yielding a :class:`_Span` for recording route plan, cost, and tokens.
    """
    return _observe("agent", name, input=input, metadata=metadata)


# ── LLM generation decorator ──────────────────────────────────────────────────


def observe_generation[**P](
    fn: Callable[P, Awaitable[LLMResponse]],
) -> Callable[P, Coroutine[Any, Any, LLMResponse]]:
    """Wrap an LLM gateway ``generate`` coroutine to emit a Langfuse generation.

    Captures the prompt, resolved model, token usage, latency, and cost. The
    provider name is read from the gateway instance (``self.name``). A pass-through
    when tracing is disabled, and the original :class:`LLMResponse` is always
    returned untouched — instrumentation never alters behavior.
    """

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> LLMResponse:
        if _client is None:
            return await fn(*args, **kwargs)

        provider = getattr(args[0], "name", "llm") if args else "llm"
        requested_model = kwargs.get("model")
        obs = _start_generation(
            name=f"{provider}.generate",
            model=requested_model if isinstance(requested_model, str) else None,
            system=kwargs.get("system"),
            messages=kwargs.get("messages"),
            max_tokens=kwargs.get("max_tokens"),
        )
        started = time.perf_counter()
        try:
            result = await fn(*args, **kwargs)
        except Exception as exc:
            _end_generation(obs, error=exc)
            raise
        _end_generation(
            obs, result=result, latency_ms=(time.perf_counter() - started) * 1000.0
        )
        return result

    return wrapper


def _start_generation(
    *,
    name: str,
    model: str | None,
    system: Any,
    messages: Any,
    max_tokens: Any,
) -> Any | None:
    """Open a Langfuse ``generation`` observation (best-effort)."""
    if _client is None:
        return None
    try:
        return _client.start_observation(
            as_type="generation",
            name=name,
            model=model,
            input={"system": system, "messages": messages},
            model_parameters=(
                {"max_tokens": max_tokens} if max_tokens is not None else None
            ),
        )
    except Exception:  # pragma: no cover - defensive
        logger.debug("Langfuse start_generation failed", exc_info=True)
        return None


def _end_generation(
    obs: Any | None,
    *,
    result: LLMResponse | None = None,
    latency_ms: float | None = None,
    error: BaseException | None = None,
) -> None:
    """Finalize a ``generation`` with usage, cost, latency, then end it."""
    if obs is None:
        return
    try:
        if error is not None:
            obs.update(level="ERROR", status_message=str(error)[:500])
        elif result is not None:
            usage = {
                "input": result.input_tokens,
                "output": result.output_tokens,
                "total": result.input_tokens + result.output_tokens,
            }
            cost = estimate_cost_usd(
                result.model, result.input_tokens, result.output_tokens
            )
            obs.update(
                output=result.text,
                model=result.model,
                usage_details=usage,
                cost_details=cost,
                metadata={
                    "stop_reason": result.stop_reason,
                    "latency_ms": round(latency_ms, 2) if latency_ms else None,
                },
            )
        obs.end()
    except Exception:  # pragma: no cover - defensive
        logger.debug("Langfuse end_generation failed", exc_info=True)
