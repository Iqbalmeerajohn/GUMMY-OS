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


# ── Phase 2: Conversation System ──────────────────────────────────────────────


class ConversationStatus(StrEnum):
    """Lifecycle status of a conversation thread (see PHASE2_PLAN.md §3)."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class AgentContext(StrEnum):
    """Which hub a thread belongs to. Forward seam for the Agent Framework;
    defaults to ``general`` until routing exists (see PHASE2_PLAN.md §3)."""

    GENERAL = "general"
    CAREER = "career"
    LEARNING = "learning"
    RESEARCH = "research"
    BUILDER = "builder"


class MessageRole(StrEnum):
    """Author role of a single message turn (see PHASE2_PLAN.md §4).

    ``tool`` is reserved for the future Agent Framework / GSD execution layer."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class SummaryType(StrEnum):
    """Kind of conversation summary (see PHASE2_PLAN.md §5)."""

    ROLLING = "rolling"
    CLOSING = "closing"


class SourceKind(StrEnum):
    """Provenance kind for a memory's source. Extensible: ``document`` and
    ``activity`` arrive in later phases (see PHASE2_PLAN.md §7)."""

    CONVERSATION = "conversation"


class ConversationSearchMode(StrEnum):
    """How to search conversations (see PHASE2_PLAN.md §4/§10)."""

    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class ConsentMode(StrEnum):
    """How automatic memory extraction may persist (memory-system §2).

    ``explicit`` — no automatic extraction (only direct "remember this").
    ``assisted`` — propose, don't auto-save (the proposal surface is future work,
      so the background consumer persists nothing in this mode for now).
    ``autonomous`` — auto-save clearly-durable facts.
    """

    EXPLICIT = "explicit"
    ASSISTED = "assisted"
    AUTONOMOUS = "autonomous"


# ── Phase 3: Agent Framework ──────────────────────────────────────────────────


class PermissionTier(StrEnum):
    """Green/Yellow/Red action tiers (see security-system.md §1).

    ``green`` — read-only / reversible, auto-allowed.
    ``yellow`` — consequential, requires confirmation (executors deferred).
    ``red`` — irreversible / sensitive, always per-action approval, no
      standing allowances (executors deferred).
    """

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class RunTrigger(StrEnum):
    """What initiated an agent run. ``scheduler`` is reserved for the future
    GSD proactive worker (PHASE3_PLAN.md §14.3)."""

    CHAT = "chat"
    SCHEDULER = "scheduler"


class RunStatus(StrEnum):
    """Lifecycle status of an ``agent_runs`` orchestration trace."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class StepStatus(StrEnum):
    """Lifecycle status of a single ``agent_steps`` agent invocation."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentMessageRole(StrEnum):
    """Kind of inter-agent hop recorded on ``agent_messages``."""

    TASK = "task"
    RESULT = "result"
    ERROR = "error"


class PlanShape(StrEnum):
    """Execution shape of a routed orchestration (PHASE3_PLAN.md §6)."""

    SINGLE = "single"
    PIPELINE = "pipeline"
    PARALLEL = "parallel"


class ToolDecision(StrEnum):
    """The policy gate's verdict recorded on a ``tool_invocations`` row.

    ``pending`` covers both the Yellow/Red "prompt the human" path and the
    Phase 3 executor-deferred case (no non-Green tool ever runs)."""

    ALLOWED = "allowed"
    BLOCKED = "blocked"
    PENDING = "pending"


class ToolRunStatus(StrEnum):
    """Execution outcome of a tool invocation (``not_executed`` for any
    blocked/pending/deferred call — the audit row still exists)."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_EXECUTED = "not_executed"


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
