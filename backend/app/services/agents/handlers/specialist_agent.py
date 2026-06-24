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

import dataclasses

from app.schemas.agents import AgentResult, AgentTask, CostInfo
from app.services.agents.prompts import PersonaBuilder
from app.services.agents.prompts.formatting import FORMATTING_RULES
from app.services.knowledge import (
    knowledge_context_builder,
    knowledge_ranker,
    knowledge_retrieval_service,
)
from app.services.knowledge.knowledge_retrieval_service import (
    UnifiedKnowledgeContext,
)
from app.services.llm.base import LLMProvider
from app.services.memory import prompt_builder
from app.services.memory.context_assembly_service import ContextPackage
from app.services.search import search_service

_EMPTY_CONTEXT = ContextPackage(memories=[], token_estimate=0)


def _web_sources(ctx: UnifiedKnowledgeContext) -> list[dict]:
    """Compact {title, url, domain} list from fused search items (B11)."""
    return [
        {
            "title": str(i.metadata.get("title", i.label)),
            "url": str(i.metadata.get("url", "")),
            "domain": str(i.metadata.get("domain", "")),
        }
        for i in ctx.search
    ]


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
    # Live web search (M8.5): supplemental context for the eligible specialists
    # (Research/Career/Learning) when the query is search-worthy. Gated + best-
    # effort inside the service; ineligible/disabled/failed → no search items, so
    # the prompt is unchanged from the search-free path (B10).
    web_results = await search_service.maybe_search(task.agent_key, task.intent)
    if web_results:
        ctx = dataclasses.replace(
            ctx,
            search=knowledge_retrieval_service.search_items_from_results(
                web_results
            ),
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
    # The specialist persona leads the system prompt, then the shared formatting
    # rules (A1: no markdown tables — stream-safe structures), then the grounded
    # prompt (knowledge + identity + summary) unchanged.
    persona = persona_fn(task.intent, compiled.block)
    lead = f"{persona}\n\n{FORMATTING_RULES}" if persona else FORMATTING_RULES
    system = f"{lead}\n\n{payload.system}"

    response = await llm.generate(system=system, messages=payload.messages)
    web_sources = _web_sources(ctx)
    return AgentResult(
        output={
            "reply": response.text,
            "model": response.model,
            "memories_used": compiled.memories_used,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            # B11: the live web sources used (for the frontend disclosure).
            "web_sources": web_sources,
        },
        citations=[{"type": "web", **s} for s in web_sources],
        cost=CostInfo(tokens=response.input_tokens + response.output_tokens),
    )
