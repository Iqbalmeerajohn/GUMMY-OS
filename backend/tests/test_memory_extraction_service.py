"""Conversation→memory extraction tests (M6): consent gate, Memory-Engine reuse,
provenance, and the re-extraction watermark."""

from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ConsentMode, MemoryCategory, MessageRole
from app.repositories import conversation_repository as conv_repo
from app.repositories import memory_repository as mem_repo
from app.repositories import memory_source_repository as src_repo
from app.repositories import message_repository as msg_repo
from app.schemas.conversation import ConversationCreate
from app.services.conversation import (
    conversation_service,
)
from app.services.conversation import (
    memory_extraction_service as extract_svc,
)
from app.services.llm.fake_provider import FakeLLMProvider


def _llm(candidates: list[dict[str, str]]) -> FakeLLMProvider:
    return FakeLLMProvider(reply=json.dumps(candidates))


async def _conv_with_messages(
    db_session: AsyncSession, user_id: uuid.UUID, count: int
) -> uuid.UUID:
    conv = await conversation_service.create_conversation(
        db_session, user_id=user_id, payload=ConversationCreate()
    )
    for i in range(count):
        await msg_repo.append_message(
            db_session,
            conversation_id=conv.id,
            user_id=user_id,
            role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
            content="I am targeting Qualcomm for an embedded role",
        )
    await db_session.commit()
    return conv.id


async def test_autonomous_extracts_via_memory_engine_with_provenance(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _conv_with_messages(db_session, seed_user, count=6)
    llm = _llm([{"content": "Targeting Qualcomm", "category": "career"}])

    created = await extract_svc.extract_and_store(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        llm=llm,
        consent_mode=ConsentMode.AUTONOMOUS,
    )
    assert len(created) == 1

    # Persisted through the Memory Engine (default scores applied).
    memories, total = await mem_repo.list_memories(
        db_session, user_id=seed_user, limit=10, offset=0
    )
    assert total == 1
    assert memories[0].content == "Targeting Qualcomm"
    assert memories[0].category is MemoryCategory.CAREER
    assert memories[0].importance_score == 0.5

    # Provenance link created (memory → conversation).
    links = await src_repo.list_for_memory(
        db_session, memory_id=created[0].id, user_id=seed_user
    )
    assert len(links) == 1
    assert links[0].conversation_id == conv_id

    # Watermark advanced to the last processed message.
    conv = await conv_repo.get_conversation(
        db_session, conversation_id=conv_id, user_id=seed_user
    )
    assert conv is not None
    assert conv.last_extracted_seq == 6


async def test_explicit_mode_extracts_nothing(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _conv_with_messages(db_session, seed_user, count=6)
    created = await extract_svc.extract_and_store(
        db_session, user_id=seed_user, conversation_id=conv_id,
        llm=_llm([{"content": "x", "category": "career"}]),
        consent_mode=ConsentMode.EXPLICIT,
    )
    assert created == []
    _, total = await mem_repo.list_memories(
        db_session, user_id=seed_user, limit=10, offset=0
    )
    assert total == 0
    conv = await conv_repo.get_conversation(
        db_session, conversation_id=conv_id, user_id=seed_user
    )
    assert conv is not None and conv.last_extracted_seq == 0  # untouched


async def test_assisted_mode_does_not_auto_save(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _conv_with_messages(db_session, seed_user, count=6)
    created = await extract_svc.extract_and_store(
        db_session, user_id=seed_user, conversation_id=conv_id,
        llm=_llm([{"content": "x", "category": "career"}]),
        consent_mode=ConsentMode.ASSISTED,
    )
    assert created == []
    _, total = await mem_repo.list_memories(
        db_session, user_id=seed_user, limit=10, offset=0
    )
    assert total == 0


async def test_single_short_exchange_is_extracted_per_turn(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    # Per-turn extraction: even a single short message is captured immediately
    # (no token/message threshold), so one-line facts persist on the first turn.
    conv_id = await _conv_with_messages(db_session, seed_user, count=1)
    created = await extract_svc.extract_and_store(
        db_session, user_id=seed_user, conversation_id=conv_id,
        llm=_llm([{"content": "Targeting Qualcomm", "category": "career"}]),
        consent_mode=ConsentMode.AUTONOMOUS,
    )
    assert len(created) == 1
    conv = await conv_repo.get_conversation(
        db_session, conversation_id=conv_id, user_id=seed_user
    )
    assert conv is not None and conv.last_extracted_seq == 1


async def test_watermark_prevents_reextraction(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _conv_with_messages(db_session, seed_user, count=6)
    llm = _llm([{"content": "Targeting Qualcomm", "category": "career"}])
    first = await extract_svc.extract_and_store(
        db_session, user_id=seed_user, conversation_id=conv_id,
        llm=llm, consent_mode=ConsentMode.AUTONOMOUS,
    )
    assert len(first) == 1

    # No new messages → empty delta → nothing extracted again (no duplicate).
    second = await extract_svc.extract_and_store(
        db_session, user_id=seed_user, conversation_id=conv_id,
        llm=llm, consent_mode=ConsentMode.AUTONOMOUS,
    )
    assert second == []
    _, total = await mem_repo.list_memories(
        db_session, user_id=seed_user, limit=10, offset=0
    )
    assert total == 1


async def test_invalid_category_is_skipped(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _conv_with_messages(db_session, seed_user, count=6)
    created = await extract_svc.extract_and_store(
        db_session, user_id=seed_user, conversation_id=conv_id,
        llm=_llm([{"content": "x", "category": "not_a_real_category"}]),
        consent_mode=ConsentMode.AUTONOMOUS,
    )
    assert created == []  # invalid category dropped
    # But the window was processed (watermark advanced) so it isn't reprocessed.
    conv = await conv_repo.get_conversation(
        db_session, conversation_id=conv_id, user_id=seed_user
    )
    assert conv is not None and conv.last_extracted_seq == 6


async def test_low_quality_candidates_are_dropped(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    # Issue 8: conversation-summary / one-time-question phrasings are rejected
    # even if the model returns them, while a real fact is kept.
    conv_id = await _conv_with_messages(db_session, seed_user, count=6)
    created = await extract_svc.extract_and_store(
        db_session, user_id=seed_user, conversation_id=conv_id,
        llm=_llm(
            [
                {"content": "User is seeking information about Vizag",
                 "category": "profile"},
                {"content": "User wants to know the weather",
                 "category": "profile"},
                {"content": "Lives in Vizag", "category": "profile"},
            ]
        ),
        consent_mode=ConsentMode.AUTONOMOUS,
    )
    assert len(created) == 1
    assert created[0].content == "Lives in Vizag"


async def test_unparseable_output_yields_nothing(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _conv_with_messages(db_session, seed_user, count=6)
    created = await extract_svc.extract_and_store(
        db_session, user_id=seed_user, conversation_id=conv_id,
        llm=FakeLLMProvider(reply="sorry, I can't do that"),
        consent_mode=ConsentMode.AUTONOMOUS,
    )
    assert created == []


async def test_code_fenced_json_is_parsed(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _conv_with_messages(db_session, seed_user, count=6)
    fenced = (
        "```json\n"
        + json.dumps([{"content": "Likes dark mode", "category": "preference"}])
        + "\n```"
    )
    created = await extract_svc.extract_and_store(
        db_session, user_id=seed_user, conversation_id=conv_id,
        llm=FakeLLMProvider(reply=fenced),
        consent_mode=ConsentMode.AUTONOMOUS,
    )
    assert len(created) == 1
    assert created[0].category is MemoryCategory.PREFERENCE
