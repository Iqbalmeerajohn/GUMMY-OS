"""End-to-end memory lifecycle tests (the birthday-recall audit).

Traces a personal fact through the full pipeline — extraction → storage (with
the right category) → retrieval → prompt injection — for the fact types a
personal AI OS must remember across conversations: birthday, age, city,
university, favorite things, project names, and career goals.

The pgvector candidate fetch is monkeypatched (SQLite can't run ``<=>``), so the
fake search returns the user's stored memories and the test asserts the *plumbing*
that the audit found broken: that an extracted fact is persisted and reaches the
prompt. The root-cause regression (consent default) is guarded directly.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.enums import ConsentMode, MemoryCategory, MessageRole
from app.models.memory import Memory
from app.repositories import memory_repository as mem_repo
from app.repositories import message_repository as msg_repo
from app.schemas.conversation import ConversationCreate
from app.services.conversation import conversation_service
from app.services.conversation import memory_extraction_service as extract_svc
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.llm.fake_provider import FakeLLMProvider
from app.services.memory import (
    context_assembly_service,
    memory_retrieval_service,
    prompt_builder,
)
from app.services.memory.context_assembly_service import ContextMemory


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
    items, _ = await mem_repo.list_memories(
        session, user_id=user_id, limit=limit, offset=0
    )
    return [(memory, 0.1 * index) for index, memory in enumerate(items)]


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


def _extracting_llm(content: str, category: MemoryCategory) -> FakeLLMProvider:
    """A fake LLM that 'extracts' exactly one durable fact (as a real one would)."""
    return FakeLLMProvider(
        reply=json.dumps([{"content": content, "category": category.value}])
    )


async def _state_fact_and_extract(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    user_message: str,
    fact: str,
    category: MemoryCategory,
) -> list[Memory]:
    """Chat 1: the user states a fact; autonomous extraction persists it."""
    conv = await conversation_service.create_conversation(
        session, user_id=user_id, payload=ConversationCreate()
    )
    await msg_repo.append_message(
        session,
        conversation_id=conv.id,
        user_id=user_id,
        role=MessageRole.USER,
        content=user_message,
    )
    await session.commit()
    return await extract_svc.extract_and_store(
        session,
        user_id=user_id,
        conversation_id=conv.id,
        llm=_extracting_llm(fact, category),
        consent_mode=ConsentMode.AUTONOMOUS,
    )


# (label, user message, stored fact, category, recall question, expected substring)
_FACTS: list[tuple[str, str, str, MemoryCategory, str, str]] = [
    (
        "birthday",
        "My birthday is July 1st.",
        "Birthday is July 1st",
        MemoryCategory.PROFILE,
        "When is my birthday?",
        "July 1st",
    ),
    (
        "age",
        "I am 27 years old.",
        "Is 27 years old",
        MemoryCategory.PROFILE,
        "How old am I?",
        "27",
    ),
    (
        "city",
        "I live in Vizag.",
        "Lives in Vizag",
        MemoryCategory.PROFILE,
        "Where do I live?",
        "Vizag",
    ),
    (
        "university",
        "I studied at IIT Madras.",
        "Studied at IIT Madras",
        MemoryCategory.LEARNING,
        "Which university did I attend?",
        "IIT Madras",
    ),
    (
        "favorite",
        "My favorite football player is Cristiano Ronaldo.",
        "Favorite football player is Cristiano Ronaldo",
        MemoryCategory.PREFERENCE,
        "Who is my favorite football player?",
        "Cristiano Ronaldo",
    ),
    (
        "project",
        "I am building GUMMY OS.",
        "Building GUMMY OS, a personal AI operating system",
        MemoryCategory.PROJECT,
        "What am I building?",
        "GUMMY OS",
    ),
    (
        "career",
        "I am targeting Qualcomm for an embedded role.",
        "Targeting Qualcomm for an embedded role",
        MemoryCategory.CAREER,
        "What job am I targeting?",
        "Qualcomm",
    ),
]


@pytest.mark.parametrize(
    "label,user_message,fact,category,question,expected",
    _FACTS,
    ids=[row[0] for row in _FACTS],
)
async def test_personal_fact_survives_the_full_lifecycle(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    label: str,
    user_message: str,
    fact: str,
    category: MemoryCategory,
    question: str,
    expected: str,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )

    # Extraction → storage.
    created = await _state_fact_and_extract(
        db_session,
        seed_user,
        user_message=user_message,
        fact=fact,
        category=category,
    )
    assert len(created) == 1, f"{label}: fact was not extracted/stored"

    # Stored with the correct category.
    memories, total = await mem_repo.list_memories(
        db_session, user_id=seed_user, limit=10, offset=0
    )
    assert total == 1
    assert memories[0].content == fact
    assert memories[0].category is category

    # Retrieval (a *later* conversation asks about it).
    ranked = await memory_retrieval_service.retrieve_memories(
        db_session,
        user_id=seed_user,
        query=question,
        embedding_service=_embeddings(),
        limit=5,
        reinforce=False,
    )
    assert any(r.memory.content == fact for r in ranked), (
        f"{label}: fact was stored but not retrievable"
    )

    # Prompt injection — the fact reaches the model.
    package = context_assembly_service.assemble_context(
        [
            ContextMemory(
                content=r.memory.content,
                category=r.memory.category.value,
                score=r.final_score,
            )
            for r in ranked
        ]
    )
    payload = prompt_builder.build_prompt(context=package, query=question)
    assert expected in payload.system, (
        f"{label}: fact was retrieved but not injected into the prompt"
    )


async def test_birthday_scenario(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat 1: 'My birthday is July 1st.' → Chat 2: 'When is my birthday?'."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _state_fact_and_extract(
        db_session,
        seed_user,
        user_message="My birthday is July 1st.",
        fact="Birthday is July 1st",
        category=MemoryCategory.PROFILE,
    )
    ranked = await memory_retrieval_service.retrieve_memories(
        db_session,
        user_id=seed_user,
        query="When is my birthday?",
        embedding_service=_embeddings(),
        limit=5,
        reinforce=False,
    )
    package = context_assembly_service.assemble_context(
        [
            ContextMemory(
                content=r.memory.content,
                category=r.memory.category.value,
                score=r.final_score,
            )
            for r in ranked
        ]
    )
    payload = prompt_builder.build_prompt(
        context=package, query="When is my birthday?"
    )
    assert "July 1st" in payload.system


async def test_startup_scenario(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat 1: 'I am building GUMMY OS.' → Chat 2: 'What startup am I building?'."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _state_fact_and_extract(
        db_session,
        seed_user,
        user_message="I am building GUMMY OS.",
        fact="Building GUMMY OS, a personal AI operating system",
        category=MemoryCategory.PROJECT,
    )
    ranked = await memory_retrieval_service.retrieve_memories(
        db_session,
        user_id=seed_user,
        query="What startup am I building?",
        embedding_service=_embeddings(),
        limit=5,
        reinforce=False,
    )
    package = context_assembly_service.assemble_context(
        [
            ContextMemory(
                content=r.memory.content,
                category=r.memory.category.value,
                score=r.final_score,
            )
            for r in ranked
        ]
    )
    payload = prompt_builder.build_prompt(
        context=package, query="What startup am I building?"
    )
    assert "GUMMY OS" in payload.system


def test_default_consent_mode_is_autonomous() -> None:
    """Root-cause regression guard.

    The audit found memories were silently dropped because the default consent
    mode was 'assisted' (which persists nothing). The code default must be
    'autonomous' so durable facts are remembered across conversations without
    any env configuration.
    """
    assert Settings.model_fields["memory_consent_mode"].default == "autonomous"


async def test_default_consent_persists_extracted_facts(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no explicit consent override, the *code default* must persist facts.

    Pins the resolved consent to the class default so the test is deterministic
    regardless of any local ``.env`` override — proving the default behavior
    (not just an explicitly-passed AUTONOMOUS) stores the fact.
    """
    default_mode = Settings.model_fields["memory_consent_mode"].default

    class _StubSettings:
        memory_consent_mode = default_mode

    monkeypatch.setattr(extract_svc, "get_settings", lambda: _StubSettings())

    conv = await conversation_service.create_conversation(
        db_session, user_id=seed_user, payload=ConversationCreate()
    )
    await msg_repo.append_message(
        db_session,
        conversation_id=conv.id,
        user_id=seed_user,
        role=MessageRole.USER,
        content="My birthday is July 1st.",
    )
    await db_session.commit()

    # consent_mode omitted → resolved from settings (the code default).
    created = await extract_svc.extract_and_store(
        db_session,
        user_id=seed_user,
        conversation_id=conv.id,
        llm=_extracting_llm("Birthday is July 1st", MemoryCategory.PROFILE),
    )
    assert len(created) == 1
    _, total = await mem_repo.list_memories(
        db_session, user_id=seed_user, limit=10, offset=0
    )
    assert total == 1
