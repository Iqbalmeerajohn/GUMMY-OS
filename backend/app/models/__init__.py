"""SQLAlchemy ORM models.

Importing this package registers every model on ``Base.metadata`` so Alembic
autogenerate and ``Base.metadata.create_all`` see the full schema.
"""

from app.database.base import Base
from app.models.action_approval import ActionApproval
from app.models.agent import Agent
from app.models.agent_message import AgentMessage
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.automation import Automation, AutomationRun
from app.models.conversation import Conversation
from app.models.conversation_summary import ConversationSummary
from app.models.conversation_summary_embedding import (
    ConversationSummaryEmbedding,
)
from app.models.enums import (
    AgentContext,
    AgentMessageRole,
    ApprovalStatus,
    ConversationStatus,
    GoalPriority,
    GoalStatus,
    MemoryCategory,
    MemoryChangeReason,
    MemoryStatus,
    MessageRole,
    PermissionTier,
    PlanShape,
    ProcessingStatus,
    RunStatus,
    RunTrigger,
    SourceKind,
    StepStatus,
    SummaryType,
    TaskStatus,
    ToolDecision,
    ToolRunStatus,
    UploadStatus,
)
from app.models.file import File
from app.models.file_chunk import FileChunk
from app.models.goal import Goal
from app.models.goal_milestone import GoalMilestone
from app.models.memory import Memory
from app.models.memory_embedding import MemoryEmbedding
from app.models.memory_source import MemorySource
from app.models.memory_version import MemoryVersion
from app.models.message import Message
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.task import Task
from app.models.tool_invocation import ToolInvocation
from app.models.user import User
from app.models.user_profile import UserProfile

__all__ = [
    "Base",
    "User",
    "PasswordResetToken",
    "RefreshToken",
    "UserProfile",
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
    "Automation",
    "AutomationRun",
    "MemorySource",
    "ConversationStatus",
    "AgentContext",
    "MessageRole",
    "SummaryType",
    "SourceKind",
    # Phase 3 — Agent Framework
    "Agent",
    "AgentRun",
    "AgentStep",
    "AgentMessage",
    "PermissionTier",
    "RunTrigger",
    "RunStatus",
    "StepStatus",
    "AgentMessageRole",
    "PlanShape",
    "ToolInvocation",
    "ToolDecision",
    "ToolRunStatus",
    "Goal",
    "GoalMilestone",
    "Task",
    "GoalStatus",
    "GoalPriority",
    "TaskStatus",
    "ActionApproval",
    "ApprovalStatus",
    # M6 — Files System
    "File",
    "FileChunk",
    "UploadStatus",
    "ProcessingStatus",
]
