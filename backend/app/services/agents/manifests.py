"""Built-in agent manifests — the code-defined Registry source of truth.

Code is the source of truth for identity/capability; the ``agents`` table
carries runtime state (``enabled``) and is re-seeded idempotently at startup.
Adding a built-in agent = adding a manifest here + a handler (M4+); never a
framework change (PHASE3_PLAN.md §5).
"""

from __future__ import annotations

from app.models.enums import PermissionTier
from app.schemas.agents import AgentManifest

# Tools every LLM-backed agent may use: read-only, local, and cheap. Declared
# once so a capability change lands on every agent that should have it rather
# than on whichever manifests someone remembered to edit.
_BASE_TOOLS: tuple[str, ...] = (
    "calculator",
    "current_time",
    "memory_read",
    "file_search",
    "file_list",
)

# Adds live web search. Only for specialists whose work genuinely needs current
# external information — search costs a network round-trip and, once a provider
# key is configured, money.
_RESEARCH_TOOLS: tuple[str, ...] = (*_BASE_TOOLS, "web_search")

GENERAL_AGENT_KEY = "general"

# The single M3 built-in: the general-purpose conversational agent. Its M4
# handler wraps the proven Phase 2 retrieve→assemble→prompt→LLM core; in M3 it
# only names the run/step the recorder writes around the legacy reply call.
GENERAL_AGENT = AgentManifest(
    key=GENERAL_AGENT_KEY,
    display_name="Gummy (General)",
    mission=(
        "Answer anything conversationally, grounded in the user's memories, "
        "thread history, and rolling summary."
    ),
    ceiling=PermissionTier.GREEN,
    tools=_BASE_TOOLS,
    keywords=(),
    model_tier="default",
)

RECALL_AGENT_KEY = "recall"

# The M5 second specialist: a read-only memory-recall agent. Deterministic
# (no LLM call): it digests the ranked memory candidates in its context pack
# into a findings block the next pipeline step grounds on. Proves routing and
# the pipeline hand-off with zero added cost or risk.
RECALL_AGENT = AgentManifest(
    key=RECALL_AGENT_KEY,
    display_name="Memory Recall",
    mission=(
        "Surface what Gummy already knows: digest the most relevant stored "
        "memories about the user's question for downstream agents."
    ),
    ceiling=PermissionTier.GREEN,
    # memory_read is the tool form of what this agent does; its handler uses
    # the pre-retrieved context pack (same retrieval service) rather than
    # re-invoking the tool, so the live path costs nothing extra. Declaring
    # it exercises registry↔catalog validation end-to-end at startup.
    tools=("memory_read",),
    keywords=(
        "remember",
        "recall",
        "memory",
        "memories",
        "what do you know",
        "what do you remember",
    ),
    model_tier="fast",
)

# ── M8 specialist workforce ──────────────────────────────────────────────────
#
# Five user-facing specialists the Router scores by keyword. Each is Green-only,
# tool-less, and LLM-backed: identity/reasoning live in its prompt builder
# (services/agents/prompts/), while grounding flows exclusively through the M7
# Unified Knowledge seam in the shared specialist handler — no agent retrieves on
# its own (Rule #1). ``priority`` breaks keyword-score ties deterministically.

CAREER_AGENT_KEY = "career"

CAREER_AGENT = AgentManifest(
    key=CAREER_AGENT_KEY,
    display_name="Career Agent",
    mission=(
        "Help the user advance their career: resumes, internships, job and "
        "internship applications, LinkedIn, salary, interview prep, and career "
        "planning — grounded in their memories, goals, and uploaded documents."
    ),
    ceiling=PermissionTier.GREEN,
    tools=_RESEARCH_TOOLS,
    keywords=(
        "resume",
        "cv",
        "internship",
        "internships",
        "job",
        "jobs",
        "application",
        "applications",
        "apply",
        "linkedin",
        "salary",
        "compensation",
        "career",
        "interview",
        "interviews",
        "recruiter",
        "hiring",
        "cover letter",
        "portfolio",
    ),
    priority=5,
    model_tier="default",
)

LEARNING_AGENT_KEY = "learning"

LEARNING_AGENT = AgentManifest(
    key=LEARNING_AGENT_KEY,
    display_name="Learning Agent",
    mission=(
        "Teach the user: explain topics, design study roadmaps and courses, and "
        "structure learning paths — grounded in what they already know and aim "
        "to learn."
    ),
    ceiling=PermissionTier.GREEN,
    tools=_RESEARCH_TOOLS,
    keywords=(
        "teach",
        "learn",
        "learning",
        "study",
        "course",
        "courses",
        "topic",
        "explain",
        "tutorial",
        "understand",
        "concept",
        "curriculum",
        "lesson",
    ),
    # Above Planner so "roadmap for deep learning" (roadmap∩planner, learning)
    # routes to Learning; Planner still wins its distinctive keywords by score.
    priority=4,
    model_tier="default",
)

PLANNER_AGENT_KEY = "planner"

PLANNER_AGENT = AgentManifest(
    key=PLANNER_AGENT_KEY,
    display_name="Planner Agent",
    mission=(
        "Turn intentions into executable plans: goals, milestones, timelines, "
        "schedules, and step-by-step roadmaps — grounded in the user's active "
        "goals and deadlines."
    ),
    ceiling=PermissionTier.GREEN,
    tools=_BASE_TOOLS,
    keywords=(
        "goal",
        "goals",
        "milestone",
        "milestones",
        "timeline",
        "plan",
        "planning",
        "schedule",
        "execution",
        "deadline",
        "roadmap",
    ),
    priority=1,
    model_tier="default",
)

MEMORY_AGENT_KEY = "memory"

MEMORY_AGENT = AgentManifest(
    key=MEMORY_AGENT_KEY,
    display_name="Memory Agent",
    mission=(
        "Answer what Gummy knows about the user: summarize their profile, "
        "history, and stored memories — grounded entirely in retrieved memory."
    ),
    ceiling=PermissionTier.GREEN,
    tools=_BASE_TOOLS,
    keywords=(
        "memory",
        "memories",
        "remember",
        "recall",
        "history",
        "profile",
        "what do you know",
        "know about me",
    ),
    priority=2,
    model_tier="default",
)

RESEARCH_AGENT_KEY = "research"

RESEARCH_AGENT = AgentManifest(
    key=RESEARCH_AGENT_KEY,
    display_name="Research Agent",
    mission=(
        "Investigate and compare: analyze options, markets, and trends, and "
        "synthesize findings — grounded in the user's knowledge (external web "
        "search arrives in M8.5)."
    ),
    ceiling=PermissionTier.GREEN,
    tools=_RESEARCH_TOOLS,
    keywords=(
        "research",
        "compare",
        "comparison",
        "analyze",
        "analysis",
        "investigate",
        "market",
        "trend",
        "trends",
        "evaluate",
        "vs",
        "versus",
    ),
    priority=3,
    model_tier="default",
)

# The Router scores against these specialists (general is the fallthrough and
# recall is an internal pipeline head — neither is a keyword target).
SPECIALIST_AGENT_KEYS: tuple[str, ...] = (
    CAREER_AGENT_KEY,
    LEARNING_AGENT_KEY,
    PLANNER_AGENT_KEY,
    MEMORY_AGENT_KEY,
    RESEARCH_AGENT_KEY,
)

BUILTIN_MANIFESTS: tuple[AgentManifest, ...] = (
    GENERAL_AGENT,
    RECALL_AGENT,
    CAREER_AGENT,
    LEARNING_AGENT,
    PLANNER_AGENT,
    MEMORY_AGENT,
    RESEARCH_AGENT,
)
