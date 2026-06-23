"""Goal & Task API tests (Phase 3, M8): endpoints, validation, tenancy."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

_TENANT = uuid.uuid4()
_OTHER = uuid.uuid4()


def _q(user: uuid.UUID = _TENANT) -> dict[str, str]:
    return {"user_id": str(user)}


async def test_goal_crud_roundtrip(api_client: AsyncClient) -> None:
    created = await api_client.post(
        "/api/v1/goals",
        params=_q(),
        json={
            "title": "Ship Phase 3",
            "priority": "high",
            "category": "work",
        },
    )
    assert created.status_code == 201
    goal = created.json()
    assert goal["status"] == "active"
    assert goal["priority"] == "high"
    assert goal["category"] == "work"
    assert goal["progress_percentage"] == 0
    assert goal["milestones"] == []

    listed = await api_client.get("/api/v1/goals", params=_q())
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    fetched = await api_client.get(
        f"/api/v1/goals/{goal['id']}", params=_q()
    )
    assert fetched.status_code == 200

    patched = await api_client.patch(
        f"/api/v1/goals/{goal['id']}",
        params=_q(),
        json={"priority": "low", "progress_percentage": 25},
    )
    assert patched.status_code == 200
    assert patched.json()["priority"] == "low"
    assert patched.json()["progress_percentage"] == 25


async def test_goal_invalid_priority_422(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/goals",
        params=_q(),
        json={"title": "g", "priority": "urgent"},
    )
    assert response.status_code == 422


async def test_goal_empty_update_400(api_client: AsyncClient) -> None:
    created = await api_client.post(
        "/api/v1/goals", params=_q(), json={"title": "g"}
    )
    goal_id = created.json()["id"]
    response = await api_client.patch(
        f"/api/v1/goals/{goal_id}", params=_q(), json={}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "empty_update"


async def test_goal_blank_title_422(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/goals", params=_q(), json={"title": "   "}
    )
    assert response.status_code == 422


async def test_goal_foreign_tenant_404(api_client: AsyncClient) -> None:
    created = await api_client.post(
        "/api/v1/goals", params=_q(), json={"title": "mine"}
    )
    goal_id = created.json()["id"]
    response = await api_client.get(
        f"/api/v1/goals/{goal_id}", params=_q(_OTHER)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "goal_not_found"
    listed = await api_client.get("/api/v1/goals", params=_q(_OTHER))
    assert listed.json()["total"] == 0


async def test_task_crud_and_transition_guard(
    api_client: AsyncClient,
) -> None:
    goal = (
        await api_client.post(
            "/api/v1/goals", params=_q(), json={"title": "g"}
        )
    ).json()
    created = await api_client.post(
        "/api/v1/tasks",
        params=_q(),
        json={"title": "t", "goal_id": goal["id"], "agent_key": "general"},
    )
    assert created.status_code == 201
    task = created.json()
    assert task["status"] == "pending"
    assert task["goal_id"] == goal["id"]

    done = await api_client.patch(
        f"/api/v1/tasks/{task['id']}",
        params=_q(),
        json={"status": "done"},
    )
    assert done.status_code == 200

    # Terminal: any further status change conflicts.
    conflict = await api_client.patch(
        f"/api/v1/tasks/{task['id']}",
        params=_q(),
        json={"status": "pending"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "invalid_task_transition"


async def test_task_list_filters(api_client: AsyncClient) -> None:
    goal = (
        await api_client.post(
            "/api/v1/goals", params=_q(), json={"title": "g"}
        )
    ).json()
    await api_client.post(
        "/api/v1/tasks",
        params=_q(),
        json={"title": "a", "goal_id": goal["id"]},
    )
    await api_client.post(
        "/api/v1/tasks", params=_q(), json={"title": "b"}
    )
    by_goal = await api_client.get(
        "/api/v1/tasks", params={**_q(), "goal_id": goal["id"]}
    )
    assert by_goal.json()["total"] == 1
    pending = await api_client.get(
        "/api/v1/tasks", params={**_q(), "status": "pending"}
    )
    assert pending.json()["total"] == 2


async def test_task_foreign_tenant_404(api_client: AsyncClient) -> None:
    created = await api_client.post(
        "/api/v1/tasks", params=_q(), json={"title": "mine"}
    )
    task_id = created.json()["id"]
    response = await api_client.get(
        f"/api/v1/tasks/{task_id}", params=_q(_OTHER)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "task_not_found"


async def test_task_foreign_goal_link_404(api_client: AsyncClient) -> None:
    goal = (
        await api_client.post(
            "/api/v1/goals", params=_q(), json={"title": "mine"}
        )
    ).json()
    response = await api_client.post(
        "/api/v1/tasks",
        params=_q(_OTHER),
        json={"title": "forged", "goal_id": goal["id"]},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "goal_not_found"
