"""Conversation search service tests (M7): hybrid ranking + score folding.

The repository's FTS/pgvector queries are PostgreSQL-only, so they're monkeypatched
to return canned hits; this exercises the pure ranking/merge logic on SQLite.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ConversationSearchMode
from app.schemas.conversation import ConversationCreate
from app.services.conversation import conversation_search_service as search_svc
from app.services.conversation import conversation_service
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


async def _new_conv(db_session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    conv = await conversation_service.create_conversation(
        db_session, user_id=user_id, payload=ConversationCreate()
    )
    return conv.id


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    keyword: list[tuple[uuid.UUID, uuid.UUID, float]],
    semantic: list[tuple[uuid.UUID, uuid.UUID, float]],
) -> None:
    async def _kw(session, *, user_id, query, limit):  # noqa: ANN001, ANN202
        return keyword

    async def _sem(session, *, user_id, query_vector, embedding_model, limit):  # noqa: ANN001, ANN202
        return semantic

    monkeypatch.setattr(
        "app.repositories.conversation_search_repository.keyword_search", _kw
    )
    monkeypatch.setattr(
        "app.repositories.conversation_search_repository.summary_semantic_search",
        _sem,
    )


async def test_keyword_mode_ranks_by_normalized_rank(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = await _new_conv(db_session, seed_user)
    c = await _new_conv(db_session, seed_user)
    await db_session.commit()
    msg_a, msg_c = uuid.uuid4(), uuid.uuid4()
    _patch(
        monkeypatch,
        keyword=[(a, msg_a, 2.0), (c, msg_c, 1.0)],
        semantic=[],
    )

    hits = await search_svc.search(
        db_session, user_id=seed_user, query="x",
        mode=ConversationSearchMode.KEYWORD, limit=10,
        embedding_service=_embeddings(),
    )
    assert [h.conversation.id for h in hits] == [a, c]
    assert hits[0].keyword_score == 1.0  # normalized (2.0 / max 2.0)
    assert hits[0].match_message_id == msg_a
    assert hits[1].semantic_score == 0.0


async def test_semantic_mode_ranks_by_similarity(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    b = await _new_conv(db_session, seed_user)
    c = await _new_conv(db_session, seed_user)
    await db_session.commit()
    _patch(
        monkeypatch,
        keyword=[],
        semantic=[(b, uuid.uuid4(), 0.2), (c, uuid.uuid4(), 0.1)],
    )

    hits = await search_svc.search(
        db_session, user_id=seed_user, query="x",
        mode=ConversationSearchMode.SEMANTIC, limit=10,
        embedding_service=_embeddings(),
    )
    # similarity = 1 - distance → c (0.9) ranks above b (0.8)
    assert [h.conversation.id for h in hits] == [c, b]
    assert hits[0].match_message_id is None  # semantic has no message anchor


async def test_hybrid_blends_keyword_and_semantic(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = await _new_conv(db_session, seed_user)  # keyword only
    b = await _new_conv(db_session, seed_user)  # semantic only
    c = await _new_conv(db_session, seed_user)  # both
    await db_session.commit()
    _patch(
        monkeypatch,
        keyword=[(a, uuid.uuid4(), 2.0), (c, uuid.uuid4(), 1.0)],
        semantic=[(b, uuid.uuid4(), 0.2), (c, uuid.uuid4(), 0.1)],
    )

    hits = await search_svc.search(
        db_session, user_id=seed_user, query="x",
        mode=ConversationSearchMode.HYBRID, limit=10,
        embedding_service=_embeddings(),
    )
    # 0.5/0.5 blend: C=0.5*0.5+0.5*0.9=0.70, A=0.5*1.0=0.50, B=0.5*0.8=0.40
    assert [h.conversation.id for h in hits] == [c, a, b]


async def test_limit_is_respected(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    convs = [await _new_conv(db_session, seed_user) for _ in range(3)]
    await db_session.commit()
    _patch(
        monkeypatch,
        keyword=[(cid, uuid.uuid4(), float(i + 1)) for i, cid in enumerate(convs)],
        semantic=[],
    )
    hits = await search_svc.search(
        db_session, user_id=seed_user, query="x",
        mode=ConversationSearchMode.KEYWORD, limit=2,
        embedding_service=_embeddings(),
    )
    assert len(hits) == 2


async def test_foreign_or_missing_conversation_is_skipped(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned = await _new_conv(db_session, seed_user)
    await db_session.commit()
    foreign = uuid.uuid4()  # not owned / does not exist
    _patch(
        monkeypatch,
        keyword=[(foreign, uuid.uuid4(), 5.0), (owned, uuid.uuid4(), 1.0)],
        semantic=[],
    )
    hits = await search_svc.search(
        db_session, user_id=seed_user, query="x",
        mode=ConversationSearchMode.KEYWORD, limit=10,
        embedding_service=_embeddings(),
    )
    # The foreign id ranked higher but is filtered by the tenant-scoped re-fetch.
    assert [h.conversation.id for h in hits] == [owned]
