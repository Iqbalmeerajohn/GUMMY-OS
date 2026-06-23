"""Goal status-action, stats, and milestone API tests (M5 Goals System)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

_TENANT = uuid.uuid4()
_OTHER = uuid.uuid4()


def _q(user: uuid.UUID = _TENANT) -> dict[str, str]:
    return {"user_id": str(user)}


async def _create_goal(api_client: AsyncClient, title: str = "g") -> dict:
    res = await api_client.post(
        "/api/v1/goals", params=_q(), json={"title": title}
    )
    assert res.status_code == 201
    return res.json()


async def test_complete_and_archive_actions(api_client: AsyncClient) -> None:
    goal = await _create_goal(api_client)

    completed = await api_client.post(
        f"/api/v1/goals/{goal['id']}/complete", params=_q()
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "completed"
    assert body["completed_at"] is not None

    archived = await api_client.post(
        f"/api/v1/goals/{goal['id']}/archive", params=_q()
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["completed_at"] is None


async def test_delete_goal(api_client: AsyncClient) -> None:
    goal = await _create_goal(api_client)
    deleted = await api_client.delete(
        f"/api/v1/goals/{goal['id']}", params=_q()
    )
    assert deleted.status_code == 204
    missing = await api_client.get(
        f"/api/v1/goals/{goal['id']}", params=_q()
    )
    assert missing.status_code == 404


async def test_goal_stats(api_client: AsyncClient) -> None:
    g1 = await _create_goal(api_client, "one")
    await _create_goal(api_client, "two")
    g3 = await _create_goal(api_client, "three")
    await api_client.post(f"/api/v1/goals/{g1['id']}/complete", params=_q())
    await api_client.post(f"/api/v1/goals/{g3['id']}/archive", params=_q())

    stats = await api_client.get("/api/v1/goals/stats", params=_q())
    assert stats.status_code == 200
    body = stats.json()
    assert body["active"] == 1
    assert body["completed"] == 1
    assert body["archived"] == 1
    assert body["total"] == 3
    # completion rate excludes archived: 1 completed / (1 active + 1 completed).
    assert body["completion_rate"] == 0.5


async def test_milestone_lifecycle_and_progress(
    api_client: AsyncClient,
) -> None:
    goal = await _create_goal(api_client)

    created = await api_client.post(
        f"/api/v1/goals/{goal['id']}/milestones",
        params=_q(),
        json={"title": "first step"},
    )
    assert created.status_code == 201
    m1 = created.json()
    assert m1["completed"] is False
    assert m1["order_index"] == 0

    m2 = (
        await api_client.post(
            f"/api/v1/goals/{goal['id']}/milestones",
            params=_q(),
            json={"title": "second step"},
        )
    ).json()

    # Complete one of two milestones → goal progress is 50%.
    done = await api_client.patch(
        f"/api/v1/milestones/{m1['id']}",
        params=_q(),
        json={"completed": True},
    )
    assert done.status_code == 200
    assert done.json()["completed"] is True
    assert done.json()["completed_at"] is not None

    fetched = await api_client.get(
        f"/api/v1/goals/{goal['id']}", params=_q()
    )
    assert fetched.json()["progress_percentage"] == 50
    assert len(fetched.json()["milestones"]) == 2

    # Deleting the incomplete milestone → 1 of 1 done → 100%.
    deleted = await api_client.delete(
        f"/api/v1/milestones/{m2['id']}", params=_q()
    )
    assert deleted.status_code == 204
    fetched = await api_client.get(
        f"/api/v1/goals/{goal['id']}", params=_q()
    )
    assert fetched.json()["progress_percentage"] == 100


async def test_milestone_blank_title_422(api_client: AsyncClient) -> None:
    goal = await _create_goal(api_client)
    res = await api_client.post(
        f"/api/v1/goals/{goal['id']}/milestones",
        params=_q(),
        json={"title": "   "},
    )
    assert res.status_code == 422


async def test_milestone_foreign_tenant_404(api_client: AsyncClient) -> None:
    goal = await _create_goal(api_client)
    res = await api_client.post(
        f"/api/v1/goals/{goal['id']}/milestones",
        params=_q(_OTHER),
        json={"title": "forged"},
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "goal_not_found"


async def test_add_milestone_to_missing_goal_404(
    api_client: AsyncClient,
) -> None:
    res = await api_client.post(
        f"/api/v1/goals/{uuid.uuid4()}/milestones",
        params=_q(),
        json={"title": "x"},
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "goal_not_found"
