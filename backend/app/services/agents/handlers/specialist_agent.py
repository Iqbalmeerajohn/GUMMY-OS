"""Shared handler for the M8 specialist agents (Career/Learning/Planner/
Memory/Research).

One pure ``AgentTask -> AgentResult`` function for all five specialists: it runs
the **same** M7 consumption seam as ``general_agent`` (adapt the context pack →
rank → compress) and the same prompt assembly, then prepends the agent's persona
to the system prompt. Per-agent identity is supplied entirely by ``persona_fn``
(from ``services/agents/prompts``); retrieval and grounding are identical across
agents — no specialist retrieves on its own (Rule #1), and execution is not
duplicated per agent (one handler, five personas).
"""

from __future__ import annotations

from app.schemas.agents import AgentResult, AgentTask, CostInfo
from app.services.agents.prompts import PersonaBuilder
from app.services.knowledge import (
    knowledge_context_builder,
    knowledge_ranker,
    knowledge_retrieval_service,
)
from app.services.llm.base import LLMProvider
from app.services.memory import prompt_builder
from app.services.memory.context_assembly_service import ContextPackage

_EMPTY_CONTEXT = ContextPackage(memories=[], token_estimate=0)


async def handle(
    task: AgentTask, *, llm: LLMProvider, persona_fn: PersonaBuilder
) -> AgentResult:
    """Ground a reply in the task's context pack, in a specialist's voice.

    Mirrors ``general_agent.handle`` exactly through the M7 seam; the only
    difference is the persona prepended to the system prompt, so grounding,
    citations, and accounting stay consistent across the workforce.
    """
    pack = task.context_pack
    ctx = knowledge_retrieval_service.context_from_pack(
        memories=list(pack.memories),
        goals=list(pack.goals),
        file_context=(
            pack.file_context if isinstance(pack.file_context, dict) else None
        ),
        query=task.intent,
    )
    ranked = knowledge_ranker.rank(ctx)
    compiled = knowledge_context_builder.build(ranked, inventory=ctx.inventory)

    history = [{str(k): str(v) for k, v in entry.items()} for entry in pack.history]
    # Pipeline hand-off (M5): fold any prior agents' findings into the summary.
    summary = pack.summary
    findings = [
        str(entry["output"].get("digest", ""))
        for entry in pack.scratch
        if isinstance(entry.get("output"), dict) and entry["output"].get("digest")
    ]
    if findings:
        block = "\n\n".join(findings)
        summary = f"{summary}\n\n{block}" if summary else block

    identity = task.inputs.get("user_identity")
    payload = prompt_builder.build_prompt(
        context=_EMPTY_CONTEXT,
        query=task.intent,
        history=history or None,
        summary=summary,
        identity=str(identity) if isinstance(identity, str) else None,
        knowledge=compiled.block,
    )
    # The specialist persona leads the system prompt; the shared grounded prompt
    # (knowledge + identity + summary) follows unchanged.
    persona = persona_fn(task.intent, compiled.block)
    system = f"{persona}\n\n{payload.system}" if persona else payload.system

    response = await llm.generate(system=system, messages=payload.messages)
    return AgentResult(
        output={
            "reply": response.text,
            "model": response.model,
            "memories_used": compiled.memories_used,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        },
        cost=CostInfo(tokens=response.input_tokens + response.output_tokens),
    )
