"""SQLAlchemy ORM models.

Importing this package registers every model on ``Base.metadata`` so Alembic
autogenerate and ``Base.metadata.create_all`` see the full schema.
"""

from app.database.base import Base
from app.models.conversation import Conversation
from app.models.conversation_summary import ConversationSummary
from app.models.conversation_summary_embedding import (
    ConversationSummaryEmbedding,
)
from app.models.enums import (
    AgentContext,
    ConversationStatus,
    MemoryCategory,
    MemoryChangeReason,
    MemoryStatus,
    MessageRole,
    SourceKind,
    SummaryType,
)
from app.models.memory import Memory
from app.models.memory_embedding import MemoryEmbedding
from app.models.memory_source import MemorySource
from app.models.memory_version import MemoryVersion
from app.models.message import Message
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Memory",
    "MemoryVersion",
    "MemoryEmbedding",
    "MemoryCategory",
    "MemoryStatus",
    "MemoryChangeReason",
    # Phase 2 — Conversation System
    "Conversation",
    "Message",
    "ConversationSummary",
    "ConversationSummaryEmbedding",
    "MemorySource",
    "ConversationStatus",
    "AgentContext",
    "MessageRole",
    "SummaryType",
    "SourceKind",
]
