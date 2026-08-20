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

from app.schemas.agents import AgentHandoff, AgentResult, AgentTask, CostInfo
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
    # The request was about the present and no live evidence backs it.
    evidence_missing: bool = False
    # Which of AVAILABLE / UNAVAILABLE / FAILED / NO_RESULTS applied.
    search_status: str = ""


# Handed to the model when the question is about the present and nothing
# current backs it. Written as an instruction about what TO write, because a
# bare prohibition gets paraphrased around rather than obeyed.
NO_EVIDENCE_DIRECTIVE = (
    "IMPORTANT — this question asks about current or recent information, and "
    "no live web results are available for it.\n"
    "Open by saying you cannot verify current information right now. Then "
    "answer only with what does not depend on being current: concepts, how "
    "things work, how the user could find out, what to look for.\n"
    "Do NOT state current facts. No specific companies, products, versions, "
    "prices, dates, funding, rankings, job openings or 'as of today' claims. "
    "Naming something you cannot check is a fabrication even if it happens to "
    "be right."
)

# Appended by code after generation, not requested from the model. A prompt
# instruction is advice a small model can drop; this sentence is present
# whatever it wrote, so the user is never left believing an unverified answer
# was checked.
#
# One per reason, because they are not the same news. "Not configured" is a
# setup step the user can take; "couldn't reach it" is worth retrying; "found
# nothing" is a fact about the search, not about us. Collapsing them into one
# message would tell the user to fix something that isn't broken.
NO_EVIDENCE_NOTICE = (
    "Live web search isn't configured on this GUMMY instance, so I can't "
    "reliably verify current information."
)
_SEARCH_FAILED_NOTICE = (
    "I couldn't reach live web search just now, so I can't reliably verify "
    "current information."
)
_NO_RESULTS_NOTICE = (
    "Live web search returned nothing for this, so I can't reliably verify "
    "current information."
)

_NOTICE_BY_STATUS: dict[str, str] = {
    "unavailable": NO_EVIDENCE_NOTICE,
    "failed": _SEARCH_FAILED_NOTICE,
    "no_results": _NO_RESULTS_NOTICE,
}


def notice_for(search_status: str) -> str:
    """The honest one-liner for why current information is unverified."""
    return _NOTICE_BY_STATUS.get(search_status, NO_EVIDENCE_NOTICE)


_NOTICE_MARKERS = (
    "live web search",
    "couldn't reach live",
    "reliably verify",
    "can't verify",
    "cannot verify",
    "can't reliably verify",
    "cannot reliably verify",
    "not configured",
)


def _needs_notice(reply: str) -> bool:
    """True when the model did not already say it cannot verify the present.

    Checked rather than always prepended, so a model that obeyed the directive
    is not made to say the same thing twice.
    """
    lowered = reply.lower()
    return not any(marker in lowered for marker in _NOTICE_MARKERS)


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
    outcome = await search_service.maybe_search_outcome(task.agent_key, task.intent)
    if outcome.results:
        ctx = dataclasses.replace(
            ctx,
            search=knowledge_retrieval_service.search_items_from_results(
                outcome.results
            ),
        )
    # A request about the present, answered with no evidence about the present.
    # This is the case the whole milestone exists for: the model will happily
    # fill the gap, and what it produces reads exactly like a finding.
    evidence_missing = (
        search_service.requires_fresh_evidence(task.intent) and not outcome.has_evidence
    )
    ranked = knowledge_ranker.rank(ctx)
    compiled = knowledge_context_builder.build(ranked, inventory=ctx.inventory)

    history = [{str(k): str(v) for k, v in entry.items()} for entry in pack.history]
    # Pipeline hand-off: fold prior agents' findings into the summary block.
    # Empty scratch (the single-agent route) leaves the prompt unchanged,
    # which is what keeps the single-agent path byte-identical.
    #
    # Two shapes are accepted. A structured ``handoff`` is what a specialist
    # produces (findings + a next action); a bare ``digest`` is what the
    # deterministic recall agent produces. Before this, only ``digest`` was
    # read — so a career->learning pipeline handed the learning agent nothing
    # at all, and it answered as though the first step had never run.
    summary = pack.summary
    findings: list[str] = []
    for entry in pack.scratch:
        handoff = entry.get("handoff")
        if isinstance(handoff, dict) and handoff.get("relevant_findings"):
            findings.append(AgentHandoff(**handoff).render())
            continue
        output = entry.get("output")
        if isinstance(output, dict) and output.get("digest"):
            findings.append(str(output["digest"]))
    if findings:
        block = (chr(10) * 2).join(findings)
        summary = f"{summary}{chr(10)*2}{block}" if summary else block

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
    if evidence_missing:
        # Appended last, which is where an instruction actually lands: placed
        # mid-prompt, guidance of this kind was measurably ignored.
        system = f"{system}\n\n{NO_EVIDENCE_DIRECTIVE}"

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
        evidence_missing=evidence_missing,
        search_status=outcome.status.value,
    )


def finish(prepared: PreparedTurn, response: LLMResponse) -> AgentResult:
    """Package a model response into the agent result contract."""
    reply = response.text
    if prepared.evidence_missing and _needs_notice(reply):
        reply = f"{notice_for(prepared.search_status)}\n\n{reply}"
    return AgentResult(
        output={
            "reply": reply,
            "model": response.model,
            "memories_used": prepared.memories_used,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "web_sources": prepared.web_sources,
            "grounding_memories": prepared.grounding_memories,
            "search_status": prepared.search_status,
            "evidence_missing": prepared.evidence_missing,
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
