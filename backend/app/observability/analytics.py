"""Product analytics — local, structured event logging.

GUMMY records what its own features do (which knowledge sources were used, which
agent ran, whether a search fired) as structured log lines on this machine. There
is no ingestion endpoint and no key to configure: usage data about a memory
product is the last thing that should leave the device.

Every entrypoint is wrapped — a product event is never worth a failed turn.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def capture_event(
    *,
    distinct_id: str,
    event: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Record a product event as a structured log line (``event=analytics``)."""
    try:
        logger.info(
            "analytics",
            extra={
                "event": "analytics",
                "analytics_event": event,
                "distinct_id": distinct_id,
                **(properties or {}),
            },
        )
    except Exception:  # pragma: no cover - defensive
        logger.debug("analytics capture failed", exc_info=True)


# ── M7 knowledge event names (single source of truth) ─────────────────────────
EVENT_KNOWLEDGE_RETRIEVED = "KnowledgeRetrieved"
EVENT_KNOWLEDGE_SOURCE_USED = "KnowledgeSourceUsed"
EVENT_KNOWLEDGE_ATTACHMENT_USED = "KnowledgeAttachmentUsed"

# ── M8 multi-agent event names (single source of truth) ───────────────────────
EVENT_AGENT_SELECTED = "AgentSelected"
EVENT_AGENT_EXECUTED = "AgentExecuted"
EVENT_AGENT_FALLBACK = "AgentFallback"
EVENT_AGENT_OVERRIDE = "AgentOverride"

# ── M8.5 web search event names (single source of truth) ──────────────────────
EVENT_SEARCH_PERFORMED = "SearchPerformed"
EVENT_SEARCH_RESULTS_RETURNED = "SearchResultsReturned"
