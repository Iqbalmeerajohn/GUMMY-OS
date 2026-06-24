"""The general-purpose conversational agent (Phase 3, M4).

A pure ``AgentTask -> AgentResult`` function. It consumes the unified knowledge
already packed onto the task (memories + goals + files) by adapting it into a
``UnifiedKnowledgeContext`` and running the **same** M7 ranker + compressor the
chat core uses — so given the same packed inputs it produces an identical
``<knowledge>`` block, prompt, and reply (the orchestration parity guarantee).
This is the M8 consumption seam: agents rank/render from the unified context
rather than retrieving each source themselves.
"""

from __future__ import annotations

from app.schemas.agents import AgentResult, AgentTask, CostInfo
from app.services.knowledge import (
    knowledge_context_builder,
    knowledge_ranker,
    knowledge_retrieval_service,
)
from app.services.llm.base import LLMProvider
from app.services.memory import prompt_builder
from app.services.memory.context_assembly_service import ContextPackage

_EMPTY_CONTEXT = ContextPackage(memories=[], token_estimate=0)


async def handle(task: AgentTask, *, llm: LLMProvider) -> AgentResult:
    """Ground a reply in the task's context pack and return it as a result."""
    pack = task.context_pack
    # Adapt the packed context into the unified shape, then rank + compress it
    # exactly as the chat core does (parity invariant).
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
    # Pipeline hand-off (M5): fold prior agents' findings into the summary
    # block. Empty scratch (the single-agent route) leaves the prompt
    # byte-identical to the chat core — the parity invariant.
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
    response = await llm.generate(system=payload.system, messages=payload.messages)
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
