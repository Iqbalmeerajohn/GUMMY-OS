"""Agent diagnostics API tests (Phase 3, M8) — ``GET /agents`` + diagnostics.

Proves the read-only routing explainer picks the right specialist for a query,
lists the available agents, and rejects a blank query — matching the live
``score_agents`` decision without executing any agent.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def test_diagnostics_selects_career(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.get(
        "/api/v1/agents/diagnostics",
        params={"user_id": str(seed_user), "q": "Review my resume"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["selected_agent"] == "career"
    assert body["confidence"] > 0
    assert "resume" in body["reason"]
    names = {a["name"] for a in body["available_agents"]}
    assert {"general", "career", "learning", "planner", "memory", "research"} <= names


async def test_diagnostics_selects_learning(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.get(
        "/api/v1/agents/diagnostics",
        params={"user_id": str(seed_user), "q": "Teach me transformers"},
    )
    assert resp.status_code == 200
    assert resp.json()["selected_agent"] == "learning"


async def test_diagnostics_vague_query_falls_back_to_general(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.get(
        "/api/v1/agents/diagnostics",
        params={"user_id": str(seed_user), "q": "tell me a joke"},
    )
    assert resp.status_code == 200
    assert resp.json()["selected_agent"] == "general"


async def test_diagnostics_rejects_blank_query(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.get(
        "/api/v1/agents/diagnostics",
        params={"user_id": str(seed_user), "q": "   "},
    )
    assert resp.status_code == 422


async def test_list_agents(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.get(
        "/api/v1/agents", params={"user_id": str(seed_user)}
    )
    assert resp.status_code == 200
    agents = resp.json()
    names = {a["name"] for a in agents}
    assert "general" in names
    assert "career" in names
    # The internal recall pipeline head is not a selectable agent.
    assert "recall" not in names
