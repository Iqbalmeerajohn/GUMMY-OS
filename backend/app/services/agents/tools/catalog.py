"""The tool catalog — every tool the framework knows, with its tier.

Code-defined (reviewable, type-checked), like agent manifests. A tool with no
executor is *modeled*: it can be declared, routed, and gated, but any attempt
to run it yields a pending/blocked audit row — never an execution. This is
how Yellow/Red capability ships ahead of the approval UI without ever firing
a risky action.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.models.enums import PermissionTier
from app.services.agents.tools.context import ToolContext


@dataclass(frozen=True)
class ToolSpec:
    """One catalog entry: identity, tier, and (for Green) an executor."""

    key: str
    tier: PermissionTier
    description: str
    # None = modeled only (no executor wired in Phase 3).
    executor: Callable[[ToolContext, dict], Awaitable[dict]] | None = None


def _catalog() -> dict[str, ToolSpec]:
    # Imported lazily so adapters can import this module's types freely.
    from app.services.agents.tools import doc_read, memory_read, web_search

    specs = (
        ToolSpec(
            key="memory_read",
            tier=PermissionTier.GREEN,
            description=(
                "Hybrid retrieval over the user's long-term memories "
                "(read-only; the Phase 1 Memory Engine)."
            ),
            executor=memory_read.execute,
        ),
        ToolSpec(
            key="web_search",
            tier=PermissionTier.GREEN,
            description=(
                "Read-only web search via the configured provider "
                "(offline-safe null provider by default)."
            ),
            executor=web_search.execute,
        ),
        ToolSpec(
            key="doc_read",
            tier=PermissionTier.GREEN,
            description=(
                "Read a stored document (read-only; the document store "
                "arrives in a later phase — empty result until then)."
            ),
            executor=doc_read.execute,
        ),
        # ── Modeled, executor-deferred (Phase 4+: approval UI first) ──────
        ToolSpec(
            key="email_send",
            tier=PermissionTier.YELLOW,
            description="Send an email on the user's behalf (DEFERRED).",
        ),
        ToolSpec(
            key="social_publish",
            tier=PermissionTier.RED,
            description="Publish content publicly (DEFERRED).",
        ),
    )
    return {spec.key: spec for spec in specs}


TOOL_CATALOG: dict[str, ToolSpec] = _catalog()

# Tool key → tier, the mapping the Registry validates manifests against.
TOOL_TIERS: dict[str, PermissionTier] = {
    key: spec.tier for key, spec in TOOL_CATALOG.items()
}
