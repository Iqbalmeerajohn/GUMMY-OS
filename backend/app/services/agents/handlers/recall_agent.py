"""The read-only memory-recall agent (Phase 3, M5).

Deterministic and LLM-free: digests the ranked memory candidates already in
the context pack into a findings block. As a pipeline head it feeds the
general agent's grounding (via the pack's ``scratch``); zero token cost,
Green-only, no side effects.
"""

from __future__ import annotations

from app.schemas.agents import AgentResult, AgentTask, CostInfo

# Cap the digest so downstream prompts stay lean.
_MAX_DIGEST_MEMORIES = 10


async def handle(task: AgentTask) -> AgentResult:
    """Digest the pack's memory candidates into a findings block."""
    memories = task.context_pack.memories[:_MAX_DIGEST_MEMORIES]
    if memories:
        lines = [
            f"- ({m['category']}) {m['content']}"
            for m in memories
        ]
        digest = "Relevant stored memories:\n" + "\n".join(lines)
    else:
        digest = "No stored memories matched this question."
    return AgentResult(
        output={
            "digest": digest,
            "memories_used": len(memories),
            # Defensive terminal reply if this agent ever ends a pipeline.
            "reply": digest,
            "model": "",
            "input_tokens": 0,
            "output_tokens": 0,
        },
        cost=CostInfo(tokens=0),
    )
