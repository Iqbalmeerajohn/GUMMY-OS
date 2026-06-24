"""Registry tests (Phase 3, M3): manifest validation, lookup, DB overlay."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PermissionTier
from app.repositories import agent_repository
from app.schemas.agents import AgentManifest
from app.services.agents.manifests import (
    BUILTIN_MANIFESTS,
    GENERAL_AGENT_KEY,
    SPECIALIST_AGENT_KEYS,
)
from app.services.agents.registry import (
    AgentRegistry,
    ManifestValidationError,
    get_registry,
)


def _manifest(key: str = "test-agent", **overrides: object) -> AgentManifest:
    fields: dict = {
        "key": key,
        "display_name": "Test Agent",
        "mission": "Test things.",
        **overrides,
    }
    return AgentManifest(**fields)


def test_builtin_registry_validates() -> None:
    registry = get_registry()
    registered = registry.keys()
    assert GENERAL_AGENT_KEY in registered
    manifest = registry.get(GENERAL_AGENT_KEY)
    assert manifest.ceiling == PermissionTier.GREEN
    assert manifest.tools == ()


def test_m8_specialists_registered_with_keywords() -> None:
    """All five M8 specialists are registered, Green-only, and have keywords."""
    registry = get_registry()
    for key in SPECIALIST_AGENT_KEYS:
        manifest = registry.get(key)
        assert manifest.ceiling == PermissionTier.GREEN
        assert manifest.keywords, f"{key} must declare routing keywords"
    assert set(SPECIALIST_AGENT_KEYS) == {
        "career",
        "learning",
        "planner",
        "memory",
        "research",
    }


def test_priority_breaks_keyword_ties() -> None:
    """Learning outranks Planner so the shared 'roadmap' keyword splits right."""
    registry = get_registry()
    assert registry.get("learning").priority > registry.get("planner").priority


def test_unknown_key_raises() -> None:
    with pytest.raises(KeyError):
        get_registry().get("nope")


def test_duplicate_key_rejected() -> None:
    with pytest.raises(ManifestValidationError, match="duplicate"):
        AgentRegistry((_manifest("dup"), _manifest("dup")))


def test_unknown_tool_rejected() -> None:
    with pytest.raises(ManifestValidationError, match="unknown tool"):
        AgentRegistry(
            (_manifest(tools=("nonexistent_tool",)),), known_tools={}
        )


def test_ceiling_below_tool_tier_rejected() -> None:
    known = {"web_publish": PermissionTier.RED}
    with pytest.raises(ManifestValidationError, match="below tool"):
        AgentRegistry(
            (
                _manifest(
                    tools=("web_publish",), ceiling=PermissionTier.GREEN
                ),
            ),
            known_tools=known,
        )


def test_ceiling_at_tool_tier_accepted() -> None:
    known = {"web_publish": PermissionTier.RED}
    registry = AgentRegistry(
        (_manifest(tools=("web_publish",), ceiling=PermissionTier.RED),),
        known_tools=known,
    )
    assert registry.get("test-agent").tools == ("web_publish",)


async def test_seed_catalog_idempotent(db_session: AsyncSession) -> None:
    registry = get_registry()
    first = await registry.seed_catalog(db_session)
    second = await registry.seed_catalog(db_session)
    assert first == second == len(BUILTIN_MANIFESTS)
    row = await agent_repository.get_by_key(db_session, GENERAL_AGENT_KEY)
    assert row is not None
    assert row.user_id is None  # global catalog row
    assert row.enabled is True


async def test_list_enabled_respects_db_overlay(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    registry = get_registry()
    await registry.seed_catalog(db_session)
    enabled = await registry.list_enabled(db_session, user_id=seed_user)
    assert {m.key for m in enabled} == {m.key for m in BUILTIN_MANIFESTS}

    row = await agent_repository.get_by_key(db_session, GENERAL_AGENT_KEY)
    assert row is not None
    row.enabled = False
    await db_session.flush()
    remaining = await registry.list_enabled(db_session, user_id=seed_user)
    assert GENERAL_AGENT_KEY not in {m.key for m in remaining}
