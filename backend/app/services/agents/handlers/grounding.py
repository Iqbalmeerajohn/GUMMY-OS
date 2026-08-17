"""Shared grounding for every LLM-backed agent handler.

``general_agent`` and ``specialist_agent`` were near-identical: both adapted the
task's context pack into the unified knowledge shape, ranked and compressed it,
folded in history/summary/identity, and built the prompt. The only differences
were the persona prepended by a specialist and the live-search fusion. Keeping
two copies meant every grounding change had to be made twice — and the M8.5
formatting-rules fix showed what happens when one copy is missed.

The work is split in two so it can be driven by a streaming *or* a
non-streaming caller without duplicating any of it:

    prepare(task)              → PreparedTurn   (all the I/O and assembly)
    finish(prepared, response) → AgentResult    (packaging only)

``handle`` is then just ``prepare → generate → finish``, while the streaming
orchestrator does ``prepare → stream → finish`` over the same prepared prompt.
One grounding implementation, two ways to consume the model's output.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

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
from app.services.llm.base import LLMProvider, LLMResponse
from app.services.memory import prompt_builder
from app.services.memory.context_assembly_service import ContextPackage
from app.services.search import search_service

_EMPTY_CONTEXT = ContextPackage(memories=[], token_estimate=0)


@dataclass(frozen=True)
class PreparedTurn:
    """A prompt ready to send, plus what the caller needs to report afterwards."""

    system: str
    messages: list[dict[str, str]]
    memories_used: int
    web_sources: list[dict] = field(default_factory=list)
    # Contents of the memories that survived compression into the prompt — what
    # the client shows in its "Memory Used" disclosure.
    grounding_memories: list[str] = field(default_factory=list)


def _web_sources(ctx: UnifiedKnowledgeContext) -> list[dict]:
    """Compact {title, url, domain} list from fused search items."""
    return [
        {
            "title": str(i.metadata.get("title", i.label)),
            "url": str(i.metadata.get("url", "")),
            "domain": str(i.metadata.get("domain", "")),
        }
        for i in ctx.search
    ]


async def prepare(
    task: AgentTask, *, persona_fn: PersonaBuilder | None = None
) -> PreparedTurn:
    """Build the grounded prompt for one agent turn.

    Live web search is attempted for every agent, because the eligibility gate
    lives in ``search_service`` and keys off the agent key — a non-eligible agent
    (general, memory, planner) gets an empty list without a network call, so the
    prompt is byte-identical to the search-free path.
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
    web_results = await search_service.maybe_search(task.agent_key, task.intent)
    if web_results:
        ctx = dataclasses.replace(
            ctx,
            search=knowledge_retrieval_service.search_items_from_results(web_results),
        )
    ranked = knowledge_ranker.rank(ctx)
    compiled = knowledge_context_builder.build(ranked, inventory=ctx.inventory)

    history = [{str(k): str(v) for k, v in entry.items()} for entry in pack.history]
    # Pipeline hand-off: fold any prior agents' findings into the summary block.
    # Empty scratch (the single-agent route) leaves the prompt unchanged.
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

    # The persona leads, then the shared formatting rules, then the grounded
    # prompt. The rules apply even without a persona: every reply the user sees
    # is rendered incrementally, and markdown tables break that renderer.
    persona = persona_fn(task.intent, compiled.block) if persona_fn else ""
    lead = f"{persona}\n\n{FORMATTING_RULES}" if persona else FORMATTING_RULES
    system = f"{lead}\n\n{payload.system}"

    return PreparedTurn(
        system=system,
        messages=payload.messages,
        memories_used=compiled.memories_used,
        web_sources=_web_sources(ctx),
        grounding_memories=[
            i.content
            for i in compiled.items
            if i.source == knowledge_retrieval_service.SOURCE_MEMORY
        ],
    )


def finish(prepared: PreparedTurn, response: LLMResponse) -> AgentResult:
    """Package a model response into the agent result contract."""
    return AgentResult(
        output={
            "reply": response.text,
            "model": response.model,
            "memories_used": prepared.memories_used,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "web_sources": prepared.web_sources,
            "grounding_memories": prepared.grounding_memories,
        },
        citations=[{"type": "web", **s} for s in prepared.web_sources],
        cost=CostInfo(tokens=response.input_tokens + response.output_tokens),
    )


async def handle(
    task: AgentTask, *, llm: LLMProvider, persona_fn: PersonaBuilder | None = None
) -> AgentResult:
    """Ground a reply and generate it in one call (the non-streaming path)."""
    prepared = await prepare(task, persona_fn=persona_fn)
    response = await llm.generate(system=prepared.system, messages=prepared.messages)
    return finish(prepared, response)
