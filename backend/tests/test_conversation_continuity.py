"""Conversation continuity tests (Req 6).

Detection of "refers to a past conversation" intent, and the prior-context block
the turn service injects when the user asks to pick up an earlier discussion.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SummaryType
from app.repositories import conversation_repository as conv_repo
from app.repositories import conversation_summary_repository as sum_repo
from app.schemas.conversation import ConversationCreate
from app.services.conversation import conversation_continuity_service as continuity
from app.services.conversation import conversation_service
from app.services.conversation.conversation_search_service import (
    ConversationSearchHit,
)
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


@pytest.mark.parametrize(
    "message,expected",
    [
        ("continue our previous discussion", True),
        ("what did we discuss yesterday?", True),
        ("tell me about the startup idea from last week", True),
        ("you mentioned a book earlier", True),
        ("pick up where we left off", True),
        ("what is the capital of France?", False),
        ("My birthday is July 1st.", False),
        ("help me plan my day", False),
    ],
)
def test_references_past_conversation(message: str, expected: bool) -> None:
    assert continuity.references_past_conversation(message) is expected


async def test_gather_returns_none_without_continuity_marker(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
) -> None:
    block = await continuity.gather_prior_context(
        db_session,
        user_id=seed_user,
        message="What is the capital of France?",
        embedding_service=_embeddings(),
    )
    assert block is None


async def test_gather_injects_relevant_prior_conversation(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A prior conversation with a rolling summary the user now refers back to.
    conv = await conversation_service.create_conversation(
        db_session, user_id=seed_user, payload=ConversationCreate()
    )
    await sum_repo.add_summary(
        db_session,
        conversation_id=conv.id,
        user_id=seed_user,
        summary_type=SummaryType.ROLLING,
        content="Discussed building GUMMY OS, a personal AI operating system.",
        version_number=1,
    )
    await db_session.commit()
    conv_obj = await conv_repo.get_conversation(
        db_session, conversation_id=conv.id, user_id=seed_user
    )
    assert conv_obj is not None

    async def _fake_search(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        query: str,
        mode: object,
        limit: int,
        embedding_service: EmbeddingService,
    ) -> list[ConversationSearchHit]:
        return [
            ConversationSearchHit(
                conversation=conv_obj,
                score=0.9,
                keyword_score=0.8,
                semantic_score=0.7,
                match_message_id=None,
            )
        ]

    monkeypatch.setattr(continuity.conversation_search_service, "search", _fake_search)

    block = await continuity.gather_prior_context(
        db_session,
        user_id=seed_user,
        message="tell me about the startup idea from last week",
        embedding_service=_embeddings(),
        current_conversation_id=None,
    )
    assert block is not None
    assert "GUMMY OS" in block


async def test_gather_excludes_the_current_conversation(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conv = await conversation_service.create_conversation(
        db_session, user_id=seed_user, payload=ConversationCreate()
    )
    await db_session.commit()
    conv_obj = await conv_repo.get_conversation(
        db_session, conversation_id=conv.id, user_id=seed_user
    )
    assert conv_obj is not None

    async def _fake_search(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        query: str,
        mode: object,
        limit: int,
        embedding_service: EmbeddingService,
    ) -> list[ConversationSearchHit]:
        return [
            ConversationSearchHit(
                conversation=conv_obj,
                score=0.9,
                keyword_score=0.8,
                semantic_score=0.7,
                match_message_id=None,
            )
        ]

    monkeypatch.setattr(continuity.conversation_search_service, "search", _fake_search)

    # The only hit is the current thread → nothing to add from "elsewhere".
    block = await continuity.gather_prior_context(
        db_session,
        user_id=seed_user,
        message="continue our previous discussion",
        embedding_service=_embeddings(),
        current_conversation_id=conv.id,
    )
    assert block is None
