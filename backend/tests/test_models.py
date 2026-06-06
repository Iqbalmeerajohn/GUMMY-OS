"""Schema/metadata tests for the relational data layer (no database required)."""

from __future__ import annotations

from app.database.base import Base
from app.models import Memory, MemoryCategory, MemoryVersion, User


def test_all_tables_registered() -> None:
    tables = set(Base.metadata.tables)
    assert {"users", "memories", "memory_versions"} <= tables


def test_user_columns() -> None:
    cols = set(Base.metadata.tables["users"].columns.keys())
    assert {"id", "email", "created_at", "updated_at"} <= cols


def test_memory_columns() -> None:
    cols = set(Base.metadata.tables["memories"].columns.keys())
    assert {
        "id",
        "user_id",
        "category",
        "content",
        "importance_score",
        "confidence_score",
        "status",
        "created_at",
        "updated_at",
    } <= cols


def test_memory_version_columns() -> None:
    cols = set(Base.metadata.tables["memory_versions"].columns.keys())
    assert {
        "id",
        "memory_id",
        "version_number",
        "content_snapshot",
        "change_reason",
        "created_at",
    } <= cols


def test_memories_indexes_present() -> None:
    index_names = {ix.name for ix in Base.metadata.tables["memories"].indexes}
    assert {
        "ix_memories_user_id",
        "ix_memories_user_id_category",
        "ix_memories_user_id_status",
    } <= index_names


def test_memory_version_unique_constraint() -> None:
    table = Base.metadata.tables["memory_versions"]
    constraint_names = {c.name for c in table.constraints}
    assert "uq_memory_versions_memory_id_version_number" in constraint_names


def test_user_memory_relationship() -> None:
    # Relationship wiring is intact in both directions.
    assert User.memories.property.mapper.class_ is Memory
    assert Memory.versions.property.mapper.class_ is MemoryVersion


def test_enum_values() -> None:
    assert MemoryCategory.CAREER.value == "career"
    assert {c.value for c in MemoryCategory} == {
        "profile",
        "preference",
        "career",
        "learning",
        "project",
        "conversation",
        "document",
    }
