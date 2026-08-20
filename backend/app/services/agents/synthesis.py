"""Synthesis — turn several parallel branch replies into one answer.

A parallel run produces two or more independent answers. Handing those to the
user stacked on top of each other is not an answer, it is a transcript of how
the work was divided — which is exactly the machinery the user should never
have to see.

This pass reads the branch replies and writes one reply. Three properties
matter more than fluency:

* **It cannot invent.** The prompt carries the branch outputs and nothing else,
  and says so. A synthesis that adds a job listing or a company that no agent
  found would be worse than no synthesis at all.
* **It cannot hide a failure.** A branch that failed is named in the prompt and
  the model is told to say so plainly. Quietly synthesising around a missing
  half produces a confident answer to half a question.
* **It cannot become a hard dependency.** Any failure here — timeout, bad
  output, no provider — falls back to :func:`compose.merge_parallel`, which is
  deterministic. Losing synthesis costs prose, never content.

The last one is why this is a separate module from ``compose``: ``compose``
stays pure and LLM-free so it remains a trustworthy floor.
"""

from __future__ import annotations

import logging

from app.schemas.agents import AgentResult
from app.services.agents import compose
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# Enough for a merged answer over two or three branches, bounded so a runaway
# generation cannot stall the turn.
MAX_SYNTHESIS_TOKENS = 900

# How much of each branch reply to hand over. Long enough to carry real
# findings, short enough that three branches still fit a small local model's
# context alongside the instructions.
MAX_BRANCH_CHARS = 3000

_SYSTEM = (
    "You are Gummy, writing the final answer to a request that was worked on "
    "in two or more parts at the same time.\n\n"
    "You are given each part's result below. Write ONE answer that covers "
    "them together.\n\n"
    "Rules:\n"
    "- Use ONLY what appears in the parts below. Do not add facts, findings, "
    "companies, roles, links, or numbers that are not there.\n"
    "- Do not mention agents, parts, steps, or how the work was divided. The "
    "user asked one question and gets one answer.\n"
    "- Keep every concrete detail from the parts — names, roles, deadlines, "
    "figures. Losing them is worse than an ugly answer.\n"
    "- If a part could not be completed, say so plainly in one sentence and "
    "never guess what it would have said.\n"
    "- Group related points together rather than repeating them per part."
)


def _prompt_body(
    results: list[tuple[str, AgentResult]],
    failures: list[tuple[str, str]],
) -> str:
    sections: list[str] = []
    for agent_key, result in results:
        reply = str(result.output.get("reply", "")).strip()
        if not reply:
            continue
        sections.append(
            f"--- {compose.heading_for(agent_key)} ---\n{reply[:MAX_BRANCH_CHARS]}"
        )
    for agent_key, _error in failures:
        sections.append(
            f"--- {compose.heading_for(agent_key)} ---\n"
            f"(This part could not be completed. Say so; do not invent it.)"
        )
    return "\n\n".join(sections)


async def synthesize_parallel(
    results: list[tuple[str, AgentResult]],
    failures: list[tuple[str, str]],
    *,
    llm: LLMProvider,
    model: str | None = None,
) -> str:
    """One answer from several branch replies.

    Falls back to the deterministic merge on any problem, including an empty or
    suspiciously short generation — a two-word "synthesis" of two full answers
    has lost the content, and the merge is strictly better than that.
    """
    fallback = compose.merge_parallel(results, failures)

    body = _prompt_body(results, failures)
    if not body.strip():
        return fallback

    try:
        response = await llm.generate(
            system=_SYSTEM,
            messages=[{"role": "user", "content": body}],
            model=model,
            max_tokens=MAX_SYNTHESIS_TOKENS,
        )
    except Exception:
        logger.exception("parallel synthesis failed; using deterministic merge")
        return fallback

    text = (response.text or "").strip()
    if len(text) < 40:
        logger.warning(
            "parallel synthesis returned %d chars; using deterministic merge",
            len(text),
        )
        return fallback
    return compose.shape_voice(text)
