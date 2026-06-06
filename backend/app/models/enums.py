"""Domain enumerations for the memory data model.

Stored as their lowercase string ``value`` in a VARCHAR column (``native_enum=
False``) — portable, migration-friendly, and validated at the application layer.
DB-level value integrity is enforced by explicit CHECK constraints on the tables.
"""

from __future__ import annotations

from enum import Enum, StrEnum

from sqlalchemy import Enum as SAEnum


class MemoryCategory(StrEnum):
    """The seven memory categories (see memory-system.md §7)."""

    PROFILE = "profile"
    PREFERENCE = "preference"
    CAREER = "career"
    LEARNING = "learning"
    PROJECT = "project"
    CONVERSATION = "conversation"
    DOCUMENT = "document"


class MemoryStatus(StrEnum):
    """Lifecycle status of a memory (see the Day-2 scope / build plan §4)."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class MemoryChangeReason(StrEnum):
    """Why a ``memory_versions`` snapshot was written."""

    CREATED = "created"
    EDITED = "edited"
    REINFORCED = "reinforced"
    CORRECTED = "corrected"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


def enum_type(enum_cls: type[Enum], name: str) -> SAEnum:
    """Build a consistent string-backed SQLAlchemy Enum column type.

    ``create_constraint=False`` — value integrity is enforced by explicit, named
    CHECK constraints on each table so names stay stable across migrations.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        length=32,
        create_constraint=False,
        validate_strings=True,
        values_callable=lambda enum: [member.value for member in enum],
    )
