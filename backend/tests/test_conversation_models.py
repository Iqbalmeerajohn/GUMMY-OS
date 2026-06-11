"""Schema/metadata tests for the Phase 2 Conversation System (no DB required).

Mirrors test_models.py: asserts the new tables, columns, indexes, constraints,
enums, and relationship wiring are registered on Base.metadata exactly as the
migrations create them.
"""

from __future__ import annotations

from app.database.base import Base
from app.models import (
    AgentContext,
    Conversation,
    ConversationStatus,
    ConversationSummary,
    ConversationSummaryEmbedding,
    Memory,
    MemorySource,
    Message,
    MessageRole,
    SourceKind,
    SummaryType,
    User,
)


def test_phase2_tables_registered() -> None:
    tables = set(Base.metadata.tables)
    assert {
        "conversations",
        "messages",
        "conversation_summaries",
        "conversation_summary_embeddings",
        "memory_sources",
    } <= tables


def test_conversation_columns() -> None:
    cols = set(Base.metadata.tables["conversations"].columns.keys())
    assert {
        "id",
        "user_id",
        "title",
        "status",
        "agent_context",
        "pinned",
        "last_message_at",
        "message_count",
        "last_extracted_seq",
        "deleted_at",
        "created_at",
        "updated_at",
    } <= cols


def test_message_columns() -> None:
    cols = set(Base.metadata.tables["messages"].columns.keys())
    assert {
        "id",
        "conversation_id",
        "user_id",
        "seq",
        "role",
        "content",
        "token_count",
        "model",
        "input_tokens",
        "output_tokens",
        "metadata",  # DB column name; attribute is `extra_metadata`
        "created_at",
    } <= cols


def test_message_seq_unique_constraint() -> None:
    table = Base.metadata.tables["messages"]
    names = {c.name for c in table.constraints}
    assert "uq_messages_conversation_id_seq" in names


def test_message_metadata_attribute_name() -> None:
    # The reserved declarative `metadata` name is mapped via `extra_metadata`.
    assert Message.extra_metadata.property.columns[0].name == "metadata"


def test_conversation_summary_columns() -> None:
    cols = set(Base.metadata.tables["conversation_summaries"].columns.keys())
    assert {
        "id",
        "conversation_id",
        "user_id",
        "summary_type",
        "content",
        "covers_through_message_id",
        "version_number",
        "model",
        "created_at",
    } <= cols


def test_conversation_summary_embedding_columns() -> None:
    table = Base.metadata.tables["conversation_summary_embeddings"]
    cols = set(table.columns.keys())
    assert {
        "id",
        "summary_id",
        "user_id",
        "embedding_model",
        "embedding_dimension",
        "content_hash",
        "embedding_vector",
        "created_at",
    } <= cols


def test_memory_source_columns() -> None:
    assert MemorySource.__tablename__ == "memory_sources"
    cols = set(Base.metadata.tables["memory_sources"].columns.keys())
    assert {
        "id",
        "user_id",
        "memory_id",
        "conversation_id",
        "message_id",
        "source_kind",
        "created_at",
    } <= cols


def test_conversation_indexes_present() -> None:
    names = {ix.name for ix in Base.metadata.tables["conversations"].indexes}
    assert {
        "ix_conversations_user_id",
        "ix_conversations_user_id_status",
        "ix_conversations_user_id_last_message_at",
        "ix_conversations_user_id_deleted_at",
    } <= names


def test_message_indexes_present() -> None:
    names = {ix.name for ix in Base.metadata.tables["messages"].indexes}
    assert {
        "ix_messages_conversation_id_created_at",
        "ix_messages_user_id",
    } <= names


def test_memory_source_indexes_present() -> None:
    names = {ix.name for ix in Base.metadata.tables["memory_sources"].indexes}
    assert {
        "ix_memory_sources_user_id",
        "ix_memory_sources_memory_id",
        "ix_memory_sources_conversation_id",
    } <= names


def test_summary_unique_constraint() -> None:
    table = Base.metadata.tables["conversation_summaries"]
    names = {c.name for c in table.constraints}
    assert (
        "uq_conversation_summaries_conversation_id_version_number" in names
    )


def test_all_identifier_names_within_postgres_limit() -> None:
    # Postgres truncates identifiers > 63 chars; guard against silent drift on
    # the new Phase 2 tables (the constraint that bit us during M1).
    phase2 = {
        "conversations",
        "messages",
        "conversation_summaries",
        "conversation_summary_embeddings",
        "memory_sources",
    }
    for name, table in Base.metadata.tables.items():
        if name not in phase2:
            continue
        for constraint in table.constraints:
            if constraint.name is not None:
                assert len(str(constraint.name)) <= 63, constraint.name
        for index in table.indexes:
            assert len(str(index.name)) <= 63, index.name


def test_relationship_wiring() -> None:
    assert Conversation.messages.property.mapper.class_ is Message
    assert Conversation.summaries.property.mapper.class_ is ConversationSummary
    assert Message.conversation.property.mapper.class_ is Conversation
    assert (
        ConversationSummary.embedding.property.mapper.class_
        is ConversationSummaryEmbedding
    )
    assert ConversationSummary.conversation.property.mapper.class_ is Conversation


def test_phase2_enum_values() -> None:
    assert {s.value for s in ConversationStatus} == {"active", "archived"}
    assert {a.value for a in AgentContext} == {
        "general",
        "career",
        "learning",
        "research",
        "builder",
    }
    assert {r.value for r in MessageRole} == {
        "user",
        "assistant",
        "system",
        "tool",
    }
    assert {t.value for t in SummaryType} == {"rolling", "closing"}
    # Phase 3 M7 widened the provenance bus (agent live; document/activity
    # reserved). 'conversation' remains the Phase 2 kind, untouched.
    assert {k.value for k in SourceKind} == {
        "conversation",
        "agent",
        "document",
        "activity",
    }


def test_phase1_models_untouched() -> None:
    # Sanity: the frozen Phase 1 models still expose their relationships and
    # were not modified to wire Phase 2 (FK-only links keep them frozen).
    assert User.memories.property.mapper.class_ is Memory
    assert not hasattr(User, "conversations")
