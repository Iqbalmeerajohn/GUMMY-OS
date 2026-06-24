# M8 — Multi-Agent Workforce

> Release notes for M8, which turns GUMMY from a single assistant into a routed
> team of specialized agents, all grounded through the M7 Unified Knowledge
> Engine. **Scope:** what shipped, the routing model, the API surface, and the
> M8.5 seam. Builds on M7 ([07/08 release notes](07_RELEASE_NOTES_M6.md)).

## What shipped

A deterministic **Agent Router** selects one of five specialists — **Career,
Learning, Planner, Memory, Research** — or falls back to the **General** agent.
Every agent grounds **only** through the M7 seam (`context_from_pack` → ranker →
compressor); no agent performs its own retrieval (the single-retrieval-layer
rule). Users let the Router decide (**Auto**) or pin an agent (**manual
override**) from the workspace selector. The whole path is traced (Langfuse) and
instrumented (PostHog), with a read-only diagnostics endpoint that explains
routing.

The work **extends the existing agent stack** (`manifests.py` / `registry.py` /
`router.py` / `orchestrator_service.py` / `handlers/`) rather than adding a
parallel one — reusing `AgentManifest`, `RoutingDecision`, `AgentResult`, and
`OrchestrationResult`. The internal `recall` pipeline agent is unchanged; the new
user-facing `memory` specialist answers "what do you know about me".

## Routing model (deterministic, no LLM)

- **Weighted keyword scoring** across specialists: a multi-word phrase match
  scores 2, a single whole-word keyword scores 1 (word-boundary matching, so
  "ex**plan**ation" never triggers Planner). Highest score wins; ties break by
  manifest `priority` then registry order.
- Below the score threshold → **General** (graceful degradation — routing never
  fails a request).
- **Manual override** bypasses scoring; an unknown agent key degrades to General.
- The `recall→general` **pipeline** is still reachable via the `research`
  thread `agent_context` hint.
- `score_agents()` is pure and free, shared by the orchestrator and the
  diagnostics endpoint so the explanation always matches live routing.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/agents` | List selectable agents (General + 5 specialists). |
| `GET` | `/api/v1/agents/diagnostics?q=<query>` | Explain the route for a query (read-only): `selected_agent`, `confidence`, `reason`, `available_agents`. |
| `POST` | `/api/v1/conversations/{id}/messages` | Turn now accepts optional `agent` (manual override; omit for Auto). |
| `POST` | `/api/v1/conversations/{id}/messages/stream` | Same `agent` override; the streamed `done` event carries the `agent` that answered. |

The agent that answered is persisted on the assistant message
(`metadata.agent_key`) so the client can badge replies.

## Observability & analytics

- **Langfuse** spans inside the orchestration trace: `agent.route`,
  `agent.execute`, `agent.response` (tagged with agent / confidence / duration).
- **PostHog** events (best-effort, never break a turn): `AgentSelected`,
  `AgentExecuted`, `AgentFallback`, `AgentOverride`. Both degrade to structured
  logs when disabled.

## Frontend

The workspace selector offers **Auto / Career / Learning / Planner / Memory /
Research**. Auto lets the Router decide; a manual pick sends `agent` on the turn.
Assistant replies show an **agent badge** sourced from the real backend decision
(`metadata.agent_key` / the stream's `agent`), falling back to the client preview
only until the reply lands.

## Search seam (prep for M8.5 — not wired)

`app/services/search/` adds the `SearchProvider` Protocol and an offline
`DummySearchProvider`. M8 ships **only the seam**; M8.5 plugs in Brave (primary)
and Tavily (fallback) via `set_provider` without touching agents.

## Tests

New: `test_agent_router`, `test_agent_executor`, the five `test_<agent>_agent`,
`test_agent_diagnostics_api`, `test_search_provider`. Extended:
`test_agent_registry`, `test_router`, the router eval, and the orchestrator
pipeline/parallel traces (now reach the recall pipeline via the research hint,
since the memory *keyword* routes to the Memory specialist).

## Behavior change

Memory keywords ("remember", "memory", "recall", …) now route to the **Memory
specialist** (a single grounded reply) instead of the internal `recall→general`
pipeline. The pipeline remains for `research` threads.
