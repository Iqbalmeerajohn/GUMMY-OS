"""PostHog product analytics — server-side event capture (best-effort).

Built on the same three principles as the Sentry and Langfuse integrations:

* **Disabled by default.** Capture is a no-op until ``POSTHOG_API_KEY`` is set,
  so local and CI runs never emit events and never need the SDK installed.
* **No secrets in the repo.** The write key comes from the environment only.
* **Best-effort.** Every entrypoint is wrapped so an analytics fault (bad key,
  SDK missing, network blip) can never propagate into a user request or a
  background worker. A product event is never worth a failed turn.

Even when PostHog is disabled, :func:`capture_event` emits a structured log line
(``event=analytics``) so the M7 knowledge events remain observable in Railway
logs without the SDK. The PostHog Python SDK is imported lazily inside
:func:`init_analytics`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

# Module-global client. ``None`` means analytics is disabled — capture falls
# back to a structured log line only.
_client: Any | None = None
_initialized = False


def init_analytics(settings: Settings) -> bool:
    """Initialize the PostHog client once. Returns True when capture is active.

    No-op (returns False) when no write key is configured. Any initialization
    error — including the SDK not being installed — is logged and swallowed so
    the app boots regardless.
    """
    global _client, _initialized
    if _initialized:
        return _client is not None
    _initialized = True

    if not settings.posthog_enabled:
        logger.info("PostHog disabled (POSTHOG_API_KEY not set)")
        return False

    try:
        from posthog import Posthog

        _client = Posthog(
            project_api_key=settings.posthog_api_key,
            host=settings.posthog_host,
        )
        logger.info("PostHog initialized (host=%s)", settings.posthog_host)
        return True
    except Exception:  # pragma: no cover - defensive
        logger.exception("PostHog init failed; continuing without analytics")
        _client = None
        return False


def is_enabled() -> bool:
    """True when a PostHog client is active and events should be sent."""
    return _client is not None


def capture_event(
    *,
    distinct_id: str,
    event: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Capture a product event (best-effort), always logging it structurally.

    A no-op for the network send when PostHog is disabled, but the event is
    still logged (``event=analytics``) so it is observable in production logs.
    Wrapped so an analytics fault never disturbs the caller — this runs on the
    request path (chat turns) and must never break a reply.
    """
    props = properties or {}
    logger.info(
        "analytics",
        extra={"event": "analytics", "analytics_event": event, **props},
    )
    if _client is None:
        return
    try:
        _client.capture(
            distinct_id=distinct_id,
            event=event,
            properties=props,
        )
    except Exception:  # pragma: no cover - defensive
        logger.debug("PostHog capture failed", exc_info=True)


def shutdown() -> None:
    """Flush and tear down the client on app shutdown (best-effort)."""
    global _client, _initialized
    if _client is not None:
        try:
            _client.shutdown()
        except Exception:  # pragma: no cover - defensive
            logger.debug("PostHog shutdown failed", exc_info=True)
    _client = None
    _initialized = False


def reset_for_tests() -> None:
    """Reset module state so a test can re-run :func:`init_analytics`."""
    global _client, _initialized
    _client = None
    _initialized = False


# ── M7 knowledge event names (single source of truth) ─────────────────────────
EVENT_KNOWLEDGE_RETRIEVED = "KnowledgeRetrieved"
EVENT_KNOWLEDGE_SOURCE_USED = "KnowledgeSourceUsed"
EVENT_KNOWLEDGE_ATTACHMENT_USED = "KnowledgeAttachmentUsed"
