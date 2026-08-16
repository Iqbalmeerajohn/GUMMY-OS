"""Goal Intelligence API tests (M5.5): conversation-detected goal candidates,
the accept/dismiss endpoints, and the consent guarantee (no auto-creation)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory
from app.models.memory import Memory
from app.repositories import memory_repository as repo

_TENANT = uuid.uuid4()


def _q(user: uuid.UUID = _TENANT, **extra: str | int) -> dict[str, str | int]:
    return {"user_id": str(user), **extra}


async def _fake_search(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query_vector: list[float],
    embedding_model: str,
    limit: int,
    include_archived: bool = False,
    category: MemoryCategory | None = None,
) -> list[tuple[Memory, float]]:
    items, _ = await repo.list_memories(session, user_id=user_id, limit=limit, offset=0)
    return [(memory, 0.1 * index) for index, memory in enumerate(items)]


async def _new_conversation(client: AsyncClient, user_id: uuid.UUID) -> str:
    resp = await client.post("/api/v1/conversations", params=_q(user_id), json={})
    return resp.json()["id"]


# ── Turn surfaces a candidate but never auto-creates ──────────────────────────


async def test_turn_surfaces_goal_candidate(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    conv_id = await _new_conversation(api_client, seed_user)

    resp = await api_client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        params=_q(seed_user),
        # Relative, not a fixed calendar date. Priority is HIGH only inside
        # HIGH_PRIORITY_WINDOW_DAYS of the target, so a hardcoded date silently
        # becomes a LOW/MEDIUM case once it drifts past that window — which is
        # exactly how this test started failing with no code change.
        json={"message": "I want to get an AI Engineer job in 2 weeks"},
    )
    assert resp.status_code == 201
    candidate = resp.json()["goal_candidate"]
    assert candidate is not None
    assert candidate["title"] == "Get an AI Engineer job"
    assert candidate["priority"] == "high"
    assert candidate["target_date"] is not None

    # Consent guarantee: detection did NOT create a goal.
    goals = await api_client.get("/api/v1/goals", params=_q(seed_user))
    assert goals.json()["total"] == 0


async def test_turn_without_goal_has_null_candidate(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    conv_id = await _new_conversation(api_client, seed_user)

    resp = await api_client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        params=_q(seed_user),
        json={"message": "What should I do today?"},
    )
    assert resp.status_code == 201
    assert resp.json()["goal_candidate"] is None


# ── Accept: explicit creation from a candidate ────────────────────────────────


async def test_accept_creates_goal_from_conversation(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.post(
        "/api/v1/goals/from-conversation",
        params=_q(),
        json={
            "title": "Get an AI Engineer job",
            "description": "I want to get an AI Engineer job by July 2nd",
            "priority": "high",
            "target_date": "2026-07-02T00:00:00Z",
            "conversation_id": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 201
    goal = resp.json()
    assert goal["title"] == "Get an AI Engineer job"
    assert goal["priority"] == "high"
    assert goal["status"] == "active"

    listed = await api_client.get("/api/v1/goals", params=_q())
    assert listed.json()["total"] == 1


async def test_accept_without_conversation_id_is_allowed(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.post(
        "/api/v1/goals/from-conversation",
        params=_q(),
        json={"title": "Launch GUMMY SaaS", "priority": "medium"},
    )
    assert resp.status_code == 201
    assert resp.json()["title"] == "Launch GUMMY SaaS"


async def test_accept_rejects_blank_title_422(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/goals/from-conversation",
        params=_q(),
        json={"title": "   ", "priority": "high"},
    )
    assert resp.status_code == 422


# ── Dismiss: records the rejection, creates nothing ───────────────────────────


async def test_dismiss_records_and_creates_nothing(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.post(
        "/api/v1/goals/from-conversation/dismiss",
        params=_q(),
        json={"title": "Get an AI Engineer job", "priority": "high"},
    )
    assert resp.status_code == 204

    listed = await api_client.get("/api/v1/goals", params=_q())
    assert listed.json()["total"] == 0
