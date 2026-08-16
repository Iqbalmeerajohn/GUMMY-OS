"""Error reporting for failures the app swallows on purpose.

Request errors surface through the exception handlers and the access log. This
helper exists for the ones that never reach a handler — background workers, the
orchestration fallback, best-effort personalization — where the alternative is a
silent `except Exception: pass`.

It writes to the local log and nowhere else. A memory product's crash reports
carry the user's own text in their context, so shipping them to a third party
would leak exactly what the local-first design protects. Every call is wrapped:
reporting a fault must never become one.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def capture_exception(
    error: BaseException,
    *,
    component: str | None = None,
    **context: Any,
) -> None:
    """Log a swallowed exception with its component tag and context."""
    try:
        logger.error(
            "captured exception in %s: %s",
            component or "unknown",
            error,
            exc_info=error,
            extra={"event": "captured_exception", "component": component, **context},
        )
    except Exception:  # pragma: no cover - defensive
        logger.debug("capture_exception failed", exc_info=True)
