"""Agent Registry — validated in-code manifests + the ``agents`` DB overlay.

Loads the built-in manifests, validates them at construction (fail fast at
startup, never per-request), and seeds/refreshes the global catalog rows so
runtime enablement lives in the DB while capability lives in code
(PHASE3_PLAN.md §5).

Tool-tier knowledge comes from the M6 tool catalog: a manifest may only
declare tools that exist there, and never above its own ceiling — the
"manifest lists a tool that doesn't exist / outranks its ceiling" failure
modes are rejected at startup.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.enums import PermissionTier
from app.repositories import agent_repository
from app.schemas.agents import AgentManifest
from app.services.agents.manifests import BUILTIN_MANIFESTS
from app.services.agents.tools.catalog import TOOL_TIERS

logger = logging.getLogger(__name__)

# Tool key → permission tier: the real M6 catalog. Manifests may only
# declare tools that exist here, at or below their ceiling.
KNOWN_TOOL_TIERS: dict[str, PermissionTier] = TOOL_TIERS

_TIER_ORDER: dict[PermissionTier, int] = {
    PermissionTier.GREEN: 0,
    PermissionTier.YELLOW: 1,
    PermissionTier.RED: 2,
}


class ManifestValidationError(ValueError):
    """A built-in manifest is malformed (duplicate key, unknown tool, or a
    ceiling below one of its tools' tiers)."""


class AgentRegistry:
    """Validated, immutable view of the agents the framework can dispatch."""

    def __init__(
        self,
        manifests: tuple[AgentManifest, ...] = BUILTIN_MANIFESTS,
        *,
        known_tools: Mapping[str, PermissionTier] | None = None,
    ) -> None:
        tools = KNOWN_TOOL_TIERS if known_tools is None else known_tools
        self._manifests: dict[str, AgentManifest] = {}
        for manifest in manifests:
            self._validate(manifest, tools)
            self._manifests[manifest.key] = manifest

    def _validate(
        self,
        manifest: AgentManifest,
        known_tools: Mapping[str, PermissionTier],
    ) -> None:
        if manifest.key in self._manifests:
            raise ManifestValidationError(
                f"duplicate agent key: {manifest.key!r}"
            )
        for tool_key in manifest.tools:
            tier = known_tools.get(tool_key)
            if tier is None:
                raise ManifestValidationError(
                    f"agent {manifest.key!r} declares unknown tool "
                    f"{tool_key!r}"
                )
            if _TIER_ORDER[tier] > _TIER_ORDER[manifest.ceiling]:
                raise ManifestValidationError(
                    f"agent {manifest.key!r} ceiling "
                    f"{manifest.ceiling.value!r} is below tool "
                    f"{tool_key!r} tier {tier.value!r}"
                )

    def get(self, agent_key: str) -> AgentManifest:
        """Return the manifest for ``agent_key`` (KeyError if unregistered)."""
        return self._manifests[agent_key]

    def keys(self) -> tuple[str, ...]:
        return tuple(self._manifests)

    async def list_enabled(
        self, session: AsyncSession, *, user_id: uuid.UUID
    ) -> list[AgentManifest]:
        """Manifests of catalog-enabled agents visible to this tenant.

        The DB overlay decides enablement; only agents with an in-code
        manifest are dispatchable (user-defined rows are a future phase).
        """
        rows: list[Agent] = await agent_repository.list_enabled(
            session, user_id=user_id
        )
        return [
            self._manifests[row.key]
            for row in rows
            if row.key in self._manifests
        ]

    async def seed_catalog(self, session: AsyncSession) -> int:
        """Idempotently upsert every built-in manifest as a global catalog row.

        Runs at startup with **no tenant GUC set** (the ``agents_global_seed``
        RLS policy path). Flush-only; the caller commits.
        """
        for manifest in self._manifests.values():
            await agent_repository.upsert_catalog(
                session,
                key=manifest.key,
                display_name=manifest.display_name,
                mission=manifest.mission,
                ceiling=manifest.ceiling,
                tool_manifest=list(manifest.tools),
                model_tier=manifest.model_tier,
            )
        return len(self._manifests)


# The process-wide registry, built (and validated) at import time.
_registry: AgentRegistry | None = None


def get_registry() -> AgentRegistry:
    """Return the validated singleton registry of built-in agents."""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry
