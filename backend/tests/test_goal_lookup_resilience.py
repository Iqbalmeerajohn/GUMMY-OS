"""Goal-lookup resilience (M5.5 hotfix): a failing active-goals query must NEVER
poison the conversation turn's transaction or cost the user a reply.

Regression for the production incident where, against a DB whose schema was
behind the code (migrations 0019/0020 unapplied), ``goal_repository.list_active``
raised mid-turn, aborting the shared transaction. The bare ``try/except`` caught
the Python error but the next write hit ``InFailedSQLTransactionError`` and the
turn crashed. The fix runs the lookup inside a SAVEPOINT so the failure is
confined and the turn proceeds.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory
from app.models.memory import Memory
from app.repositories import memory_repository as repo
from app.schemas.conversation import ConversationCreate
from app.services.conversation import conversation_service
from app.services.knowledge import knowledge_retrieval_service


async def _boom_list_active(
    session: AsyncSession, *, user_id: uuid.UUID, limit: int
) -> list:
    """Stand-in for a goal query that fails against a schema behind the code.

    Executes real failing SQL so the *transaction-poisoning* path is exercised,
    not merely a raised Python exception."""
    await session.execute(sa.text("SELECT * FROM __missing_goal_table__"))
    return []


async def test_failed_goal_lookup_keeps_session_usable(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.goal_repository.list_active", _boom_list_active
    )

    # The lookup fails internally but degrades to no goals (never raises). M7
    # moved the SAVEPOINT-isolated active-goals lookup into the unified knowledge
    # engine; the resilience contract is unchanged.
    goals = await knowledge_retrieval_service._retrieve_goals(
        db_session, user_id=seed_user
    )
    assert goals == []

    # The savepoint confined the failure: the outer transaction is still usable…
    assert (await db_session.execute(sa.text("SELECT 1"))).scalar() == 1

    # …and a real write + commit still succeeds (transaction not poisoned).
    conversation = await conversation_service.create_conversation(
        db_session, user_id=seed_user, payload=ConversationCreate()
    )
    await db_session.commit()
    assert conversation.id is not None


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
    items, _ = await repo.list_memories(
        session, user_id=user_id, limit=limit, offset=0
    )
    return [(memory, 0.1 * index) for index, memory in enumerate(items)]


async def test_turn_completes_when_goal_lookup_fails(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: a turn still returns a persisted reply when the goal lookup
    blows up, proving Goal Intelligence cannot take chat down."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    monkeypatch.setattr(
        "app.repositories.goal_repository.list_active", _boom_list_active
    )

    conv = await api_client.post(
        "/api/v1/conversations",
        params={"user_id": str(seed_user)},
        json={},
    )
    conv_id = conv.json()["id"]

    resp = await api_client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        params={"user_id": str(seed_user)},
        json={"message": "I want to get an AI Engineer job by July 2nd"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["reply"]
    assert body["message_count"] == 2
    # Detection itself (pure, no DB) is unaffected and still surfaces.
    assert body["goal_candidate"] is not None
