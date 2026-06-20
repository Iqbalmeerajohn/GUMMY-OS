"""Sentry monitoring — initialization and a best-effort capture helper.

Monitoring is fully disabled (a no-op) when ``SENTRY_DSN`` is unset, so local and
CI runs never emit events. Every public function here is wrapped so a monitoring
fault can never propagate into a user flow or a background worker.

FastAPI request errors are captured automatically by the Sentry integrations.
``capture_exception`` exists for the failures the app *swallows on purpose*
(background workers, the orchestration fallback) — those never reach the request
handler, so they must be reported explicitly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

_initialized = False


def init_sentry(settings: Settings) -> bool:
    """Initialize Sentry once. Returns True when monitoring is active.

    No-op (returns False) when no DSN is configured. Any initialization error is
    logged and swallowed — the app must boot even if monitoring can't.
    """
    global _initialized
    if _initialized:
        return True
    if not settings.sentry_dsn:
        logger.info("Sentry disabled (no SENTRY_DSN configured)")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.asyncio import AsyncioIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment or settings.app_env,
            release=settings.version,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            profiles_sample_rate=settings.sentry_profiles_sample_rate,
            # GUMMY stores private user data; never attach IP/cookies/headers.
            send_default_pii=False,
            integrations=[
                StarletteIntegration(),
                FastApiIntegration(),
                AsyncioIntegration(),
            ],
        )
        _initialized = True
        logger.info(
            "Sentry initialized (env=%s, traces=%.2f)",
            settings.sentry_environment or settings.app_env,
            settings.sentry_traces_sample_rate,
        )
        return True
    except Exception:  # pragma: no cover - defensive
        logger.exception("Sentry init failed; continuing without monitoring")
        return False


def capture_exception(
    error: BaseException,
    *,
    component: str | None = None,
    **context: Any,
) -> None:
    """Report a swallowed exception to Sentry, tagged for triage.

    A no-op when Sentry is uninitialized (``capture_exception`` has no active
    client). Wrapped so a monitoring fault never disturbs the caller — this is
    invoked from background workers and fallback paths that must keep running.
    """
    try:
        import sentry_sdk

        with sentry_sdk.new_scope() as scope:
            if component is not None:
                scope.set_tag("component", component)
            for key, value in context.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_exception(error)
    except Exception:  # pragma: no cover - defensive
        logger.debug("Sentry capture_exception failed", exc_info=True)
