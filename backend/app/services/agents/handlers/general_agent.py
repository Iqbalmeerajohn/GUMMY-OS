"""The general-purpose conversational agent (Phase 3, M4).

A pure ``AgentTask -> AgentResult`` function that reuses the proven Phase 2
core verbatim: context assembly (token budgeting/dedupe) → prompt builder →
LLM. Given the same ranked memory candidates, history, and summary that
``generate_grounded_reply`` uses, it produces an **identical** prompt and
therefore an identical reply — the M4 parity guarantee.
"""

from __future__ import annotations

from app.core.constants import (
    DEFAULT_CONTEXT_MAX_MEMORIES,
    DEFAULT_CONTEXT_TOKEN_BUDGET,
)
from app.schemas.agents import AgentResult, AgentTask, CostInfo
from app.services.llm.base import LLMProvider
from app.services.memory import context_assembly_service, prompt_builder
from app.services.memory.context_assembly_service import ContextMemory


async def handle(task: AgentTask, *, llm: LLMProvider) -> AgentResult:
    """Ground a reply in the task's context pack and return it as a result."""
    pack = task.context_pack
    candidates = [
        ContextMemory(
            content=str(m["content"]),
            category=str(m["category"]),
            score=float(m["score"]),
        )
        for m in pack.memories
    ]
    token_budget = int(
        task.inputs.get("token_budget", DEFAULT_CONTEXT_TOKEN_BUDGET)
    )
    max_memories = int(
        task.inputs.get("max_memories", DEFAULT_CONTEXT_MAX_MEMORIES)
    )
    package = context_assembly_service.assemble_context(
        candidates,
        token_budget=token_budget,
        max_memories=max_memories,
    )
    history = [
        {str(k): str(v) for k, v in entry.items()} for entry in pack.history
    ]
    # Pipeline hand-off (M5): fold prior agents' findings into the summary
    # block. Empty scratch (the single-agent route) leaves the prompt
    # byte-identical to the legacy core — the parity invariant.
    summary = pack.summary
    findings = [
        str(entry["output"].get("digest", ""))
        for entry in pack.scratch
        if isinstance(entry.get("output"), dict)
        and entry["output"].get("digest")
    ]
    if findings:
        block = "\n\n".join(findings)
        summary = f"{summary}\n\n{block}" if summary else block
    identity = task.inputs.get("user_identity")
    # Goal awareness (M5.5): surface the user's active goals (already packed by
    # the context builder) so the agent can reference them when relevant. Empty
    # goals leave the prompt byte-identical to the legacy core.
    goals = [
        {
            "title": g.get("title", ""),
            "priority": g.get("priority", "medium"),
            "target_date": g.get("target_date"),
            "progress_percentage": g.get("progress_percentage", 0),
        }
        for g in pack.goals
    ]
    payload = prompt_builder.build_prompt(
        context=package,
        query=task.intent,
        history=history or None,
        summary=summary,
        identity=str(identity) if isinstance(identity, str) else None,
        goals=goals or None,
    )
    response = await llm.generate(
        system=payload.system, messages=payload.messages
    )
    return AgentResult(
        output={
            "reply": response.text,
            "model": response.model,
            "memories_used": len(package.memories),
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        },
        cost=CostInfo(
            tokens=response.input_tokens + response.output_tokens
        ),
    )
