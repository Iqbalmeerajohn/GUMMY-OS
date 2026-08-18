"""The tool loop — reason, call, observe, continue.

One agent turn becomes a bounded conversation with the model:

    prompt + tools -> model
      final answer?            -> done
      tool calls?              -> gate each, execute, feed results back, repeat

Everything that makes this safe lives elsewhere and is reused here rather than
re-implemented: ``interface.invoke`` is still the only door to a tool (manifest
check, policy verdict, audit row), ``executor.run`` still owns validation and the
timeout. This module owns only the *cycle* — how many turns, what the model is
shown, and when to stop.

Three bounds, each for a different failure:

* **iterations** — a model that keeps calling tools instead of answering. It is
  told when it has one iteration left and asked to answer with what it has, so
  the cap produces a real answer rather than a truncated one.
* **calls per step** — a model that fans out a dozen calls at once, which is
  usually a misunderstanding rather than a plan.
* **per-tool timeout** — enforced by the executor, so no tool can hold the loop.

The model never sees a tier, an approval id, or an internal error. It sees what
it asked for and what came back.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MAX_TOOL_CALLS_PER_STEP, MAX_TOOL_ITERATIONS
from app.services.agents.tools import catalog, interface
from app.services.agents.tools.context import ToolContext
from app.services.agents.tools.executor import ToolExecution, ToolOutcome
from app.services.llm.base import (
    SupportsToolCalling,
    ToolCall,
    ToolCallResponse,
)

logger = logging.getLogger(__name__)

# Appended for the model's last permitted iteration. Without it the loop simply
# stops mid-investigation and the user gets whatever half-thought was in flight.
_FINAL_ITERATION_NOTE = (
    "\n\nYou have no further tool calls available. Answer now using what you "
    "already have, and say plainly if something could not be determined."
)


@dataclass
class ToolLoopResult:
    """The outcome of running one agent turn through the loop."""

    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    iterations: int = 0
    executions: list[ToolExecution] = field(default_factory=list)
    hit_iteration_cap: bool = False

    @property
    def used_tools(self) -> bool:
        return bool(self.executions)


def _result_message(call: ToolCall, execution: ToolExecution) -> dict:
    """The ``tool`` message carrying one result back to the model."""
    return {
        "role": "tool",
        "tool_call_id": call.id,
        "name": call.name,
        "content": json.dumps(execution.for_model(), default=str),
    }


def _assistant_message(response: ToolCallResponse) -> dict:
    """Echo the model's own tool-calling turn back into the history.

    Required by the chat format: a ``tool`` message is only meaningful as a
    reply to the assistant turn that requested it. Omitting this makes the
    model re-issue the same calls, which is exactly the infinite loop the
    iteration cap exists to catch — better not to cause it.
    """
    return {
        "role": "assistant",
        "content": response.text,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in response.tool_calls
        ],
    }


async def run_tool_loop(
    session: AsyncSession,
    *,
    system: str,
    messages: list[dict],
    tool_keys: tuple[str, ...] | list[str],
    llm: object,
    agent_key: str,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    context: ToolContext,
    standing_allowances: frozenset[str] = frozenset(),
    max_iterations: int = MAX_TOOL_ITERATIONS,
) -> AsyncIterator[dict]:
    """Run the loop, yielding progress events then exactly one ``result``.

    Events (all safe to display — a tool name and a status, never reasoning):

    * ``{"type": "tool_status", "stage": "tool_requested"|"tool_running"|
      "tool_completed"|"tool_failed"|"approval_required", "tool": key, ...}``
    * ``{"type": "result", "result": ToolLoopResult}`` — once, last.

    Yields the result unchanged when the provider cannot call tools or the agent
    declares none, so callers need no special case for the tool-less path.
    """
    schemas = catalog.function_schemas(tool_keys)
    if not schemas or not isinstance(llm, SupportsToolCalling):
        # No tools to offer, or a provider that cannot use them. Either way this
        # is a normal turn; the caller's non-tool path handles it.
        yield {"type": "result", "result": None}
        return

    history = list(messages)
    executions: list[ToolExecution] = []
    total_input = 0
    total_output = 0
    iteration = 0
    hit_cap = False
    response: ToolCallResponse | None = None

    while iteration < max_iterations:
        iteration += 1
        is_final = iteration == max_iterations
        step_system = system + (_FINAL_ITERATION_NOTE if is_final else "")

        response = await llm.generate_with_tools(
            system=step_system,
            messages=history,
            tools=schemas,
        )
        total_input += response.input_tokens
        total_output += response.output_tokens

        if not response.wants_tools:
            break

        # A burst of calls is capped rather than refused: the first few are
        # usually the useful ones, and refusing outright wastes the turn.
        calls = response.tool_calls[:MAX_TOOL_CALLS_PER_STEP]
        if len(response.tool_calls) > MAX_TOOL_CALLS_PER_STEP:
            logger.warning(
                "agent %s requested %d tool calls; running the first %d",
                agent_key,
                len(response.tool_calls),
                MAX_TOOL_CALLS_PER_STEP,
            )

        history.append(_assistant_message(response))

        for call in calls:
            yield {
                "type": "tool_status",
                "stage": "tool_requested",
                "tool": call.name,
            }
            spec = catalog.get(call.name)
            yield {
                "type": "tool_status",
                "stage": "tool_running",
                "tool": call.name,
                "label": spec.name if spec else call.name,
            }

            # The single door: manifest check, policy gate, audit row, execute.
            gate = await interface.invoke(
                session,
                tool_key=call.name,
                args=call.arguments,
                agent_key=agent_key,
                run_id=run_id,
                user_id=user_id,
                context=context,
                standing_allowances=standing_allowances,
            )
            execution = gate.execution()
            executions.append(execution)

            if execution.outcome is ToolOutcome.APPROVAL_REQUIRED:
                yield {
                    "type": "tool_status",
                    "stage": "approval_required",
                    "tool": call.name,
                    "label": spec.name if spec else call.name,
                    "approval_id": str(execution.approval_id or ""),
                }
            elif execution.ok:
                yield {
                    "type": "tool_status",
                    "stage": "tool_completed",
                    "tool": call.name,
                    "label": spec.name if spec else call.name,
                    "duration_ms": round(execution.duration_ms, 1),
                }
            else:
                yield {
                    "type": "tool_status",
                    "stage": "tool_failed",
                    "tool": call.name,
                    "label": spec.name if spec else call.name,
                    "status": execution.outcome.value,
                }

            # Every outcome goes back to the model, including the refusals. An
            # agent told "that needs your approval" can explain itself; an agent
            # told nothing invents a result.
            history.append(_result_message(call, execution))
    else:
        # Loop exhausted without break: the model still wanted tools on its
        # final permitted iteration.
        hit_cap = True
        logger.warning(
            "agent %s hit the tool iteration cap (%d)", agent_key, max_iterations
        )

    text = response.text if response else ""
    if hit_cap and not text:
        # The cap fired and the model produced no prose. Say so plainly rather
        # than returning an empty bubble.
        text = (
            "I gathered what I could but wasn't able to finish that "
            "investigation. Could you narrow the question a little?"
        )

    yield {
        "type": "result",
        "result": ToolLoopResult(
            text=text,
            model=response.model if response else "",
            input_tokens=total_input,
            output_tokens=total_output,
            iterations=iteration,
            executions=executions,
            hit_iteration_cap=hit_cap,
        ),
    }
