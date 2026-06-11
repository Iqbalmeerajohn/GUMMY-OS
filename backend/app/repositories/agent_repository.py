"""Data-access layer for the agents registry catalog (persistence only).

Catalog rows mirror the in-code manifests (code is the source of truth; the
row carries runtime state such as ``enabled``). Global built-in agents have
``user_id IS NULL``; tenant rows are reserved for user-defined agents in a
later phase. No commit here — callers own the unit of work.
"""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.enums import PermissionTier


async def get_by_key(session: AsyncSession, key: str) -> Agent | None:
    """Fetch a catalog row by its unique key (global rows included via RLS)."""
    stmt = select(Agent).where(Agent.key == key)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_enabled(
    session: AsyncSession, *, user_id: uuid.UUID | None = None
) -> list[Agent]:
    """Return enabled agents visible to a tenant: global rows plus their own.

    ``user_id=None`` returns only the global catalog (the seed/startup view).
    """
    visibility = (
        Agent.user_id.is_(None)
        if user_id is None
        else or_(Agent.user_id.is_(None), Agent.user_id == user_id)
    )
    stmt = (
        select(Agent)
        .where(Agent.enabled.is_(True), visibility)
        .order_by(Agent.key.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def upsert_catalog(
    session: AsyncSession,
    *,
    key: str,
    display_name: str,
    mission: str,
    ceiling: PermissionTier,
    tool_manifest: list[str],
    model_tier: str | None = None,
) -> Agent:
    """Insert or refresh a **global** catalog row from an in-code manifest.

    Identity/capability fields follow the manifest on every startup;
    ``enabled`` is runtime state and is preserved on existing rows (a manual
    disable survives a redeploy). Flush-only; idempotent per key.
    """
    existing = await get_by_key(session, key)
    if existing is not None:
        existing.display_name = display_name
        existing.mission = mission
        existing.ceiling = ceiling
        existing.tool_manifest = list(tool_manifest)
        existing.model_tier = model_tier
        await session.flush()
        return existing
    agent = Agent(
        user_id=None,
        key=key,
        display_name=display_name,
        mission=mission,
        ceiling=ceiling,
        tool_manifest=list(tool_manifest),
        model_tier=model_tier,
        enabled=True,
    )
    session.add(agent)
    await session.flush()
    return agent
