"""Built-in agent manifests — the code-defined Registry source of truth.

Code is the source of truth for identity/capability; the ``agents`` table
carries runtime state (``enabled``) and is re-seeded idempotently at startup.
Adding a built-in agent = adding a manifest here + a handler (M4+); never a
framework change (PHASE3_PLAN.md §5).
"""

from __future__ import annotations

from app.models.enums import PermissionTier
from app.schemas.agents import AgentManifest

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
    tools=(),
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
    tools=(),
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

BUILTIN_MANIFESTS: tuple[AgentManifest, ...] = (GENERAL_AGENT, RECALL_AGENT)
