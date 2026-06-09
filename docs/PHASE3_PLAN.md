# GUMMY OS — Phase 3 Plan: Agent Framework / Master Orchestrator

**Status:** Design of record (architecture only). No implementation code.
**Builds on:** Phase 1 Memory Engine, Phase 1.5 JWT + RLS, Phase 2 Conversation System
(tag `phase2-complete`, migration head `0011_extraction_watermark`).
**Insertion point:** [conversation_turn_service.run_turn](../backend/app/services/conversation/conversation_turn_service.py)
— today it calls one grounded-reply pipeline; Phase 3 lets it call a **Master
Orchestrator** that routes to agents. Persistence, summaries, and extraction stay
agent-agnostic and unchanged.

> **Scope guardrail.** This document is a *complete architecture design only*. It does
> not modify any existing system, change any schema, or write implementation code. Every
> "Impact" section below describes a **planned** change to be made in a later build, not
> a change made now. The Phase 2 turn pipeline remains the live path until Phase 3 ships
> behind a feature flag (see §15 Migration Roadmap).

This realizes the vision in [../architecture/agent-framework.md](../architecture/agent-framework.md)
and [../architecture/system-design.md](../architecture/system-design.md) §3, on top of
the concrete layering proven in Phase 2 ([PHASE2_ARCHITECTURE.md](PHASE2_ARCHITECTURE.md)).

---

## 1. Roadmap reconciliation

The aspirational [ROADMAP.md](ROADMAP.md) labels "Phase 2" as the Career Agent. The
**built** sequence diverged: Phase 1 = Memory Engine, Phase 1.5 = JWT + RLS, Phase 2 =
Conversation System. **Phase 3 (this document) is the Agent Framework / Master
Orchestrator** — the substrate that *every* domain agent (Career, Learning, Research,
…) plugs into. It must exist before any single specialist agent, otherwise each agent
reinvents routing, context, tools, and policy.

So Phase 3 deliberately ships **the framework plus a thin set of "trivial" agents**
(see §15) to prove the contract end-to-end, while deferring the rich domain agents
(Career, Learning, Fitness, Marketing, Research, Business) to Phase 4+. Those domain
agents are covered here only under **Future Compatibility** (§14) — to prove the
contract is sufficient for them — not as Phase 3 deliverables.

---

## 2. Design principles

These extend, never contradict, the Phase 2 engineering rules.

1. **Orchestrator is the only new entrypoint.** `run_turn` keeps its signature; behind a
   flag it delegates to the Orchestrator instead of `generate_grounded_reply`. No new
   public HTTP surface is *required* in the first cut.
2. **Agents are stateless and ephemeral.** All durable state lives in Postgres (memory,
   messages, goals, tasks, runs). An agent is a pure function of
   `(task, context_pack, tools)` → `typed result`. This is what makes them
   horizontally scalable ([agent-framework.md](../architecture/agent-framework.md) §8).
3. **One typed contract.** Every agent receives `AgentTask` and returns `AgentResult`
   (§9). Adding an agent is registering a row + a handler, never a framework change.
4. **Reuse the Memory Engine and Conversation System verbatim.** Memory read/write goes
   through `memory_service` / `memory_retrieval_service`; context assembly reuses
   `context_assembly_service` + `prompt_builder`. The Orchestrator composes these, it
   does not reimplement them.
5. **Policy is central, never per-agent.** The Green/Yellow/Red gate
   ([security-system.md](../architecture/security-system.md) §1) lives in the
   Orchestrator/policy engine. Agents *propose* actions; they never execute Red/Yellow
   directly. An agent's declared **permission ceiling** is enforced outside its code.
6. **Layering rule holds.** HTTP thin → services own business logic + the unit of work
   (commit) → repositories flush-only → workers run off the request path. The
   Orchestrator is a **service**, agents are **services**, the policy engine is a
   **service**; new tables get repositories; long agent runs go to a worker.
7. **Tenant isolation is non-negotiable.** Every new table carries a denormalized
   `user_id` and a fail-closed direct-column RLS policy, granted to `gummy_app` in the
   migration — exactly the Phase 2 pattern. An agent only ever sees the requesting
   tenant's data.
8. **Untrusted external content cannot escalate.** Tool output (web, files) is data, not
   instructions; it can inform an answer but can never lift an agent's ceiling or
   approve a Red action (prompt-injection defense).
9. **Observable by construction.** Every orchestration is a traced, costed `agent_run`
   row + child `agent_steps`. Cost and latency are first-class, not afterthoughts.

---

## 3. Target architecture

```
   Client ── Bearer JWT ──▶ FastAPI  /api/v1/conversations/{id}/messages
                                   │ get_current_user → tenant ContextVar (unchanged)
                                   ▼
                    conversation_turn_service.run_turn          ← Phase 2 entrypoint
                                   │  (feature flag: orchestrated?)
                 ┌─────────────────┴─────────────────┐
                 │ legacy: generate_grounded_reply    │  (kept; default off-flag)
                 ▼ orchestrated:                      ▼
        ┌───────────────────────  MASTER ORCHESTRATOR  ───────────────────────┐
        │  1 intent parse → 2 plan → 3 context → 4 dispatch → 5 gate →         │
        │  6 compose → 7 persist + audit            (app/services/agents/)      │
        └───┬───────────┬──────────────┬───────────────┬──────────────┬────────┘
            │           │              │               │              │
            ▼           ▼              ▼               ▼              ▼
       Agent       Agent         Agent Context    Policy Engine   Agent Run
       Registry    Router        Builder          (G/Y/R gate)    Recorder
            │           │              │               │              │
            └─────┬─────┴──────┬───────┴───────┬───────┴──────────────┘
                  ▼            ▼               ▼
            Agent Runtime  Tool Execution   Shared Agent Memory Access
            (handlers)     Interface         (read/write via Memory Engine)
                  │            │               │
                  ▼            ▼               ▼
        ┌──────── Reused, unchanged ────────────────────────────────────────┐
        │ memory_service · memory_retrieval_service · context_assembly_service│
        │ prompt_builder · embedding_service · llm gateway · enrichment_worker│
        └────────────────────────────────────────────────────────────────────┘
                  │
                  ▼
   PostgreSQL (gummy_app, NOBYPASSRLS) — Phase 1/2 tables + NEW Phase 3 tables:
   agents(registry) · agent_runs · agent_steps · agent_messages ·
   goals · tasks · tool_invocations · action_approvals
   (every table: user_id + fail-closed RLS + gummy_app grant)
```

**Agent-to-agent communication** (§8) flows *only through the Orchestrator* in Phase 3
(no peer side-channels), persisted as `agent_messages` for traceability.

---

## 4. Core Component — Master Orchestrator

### 4.1 Purpose
The conductor and single internal entrypoint for intent. Replaces the straight-line
`generate_grounded_reply` call inside `run_turn` with a routed, multi-agent pipeline
that still produces one coherent Gummy reply.

### 4.2 Responsibilities
1. **Intent parse** — interpret the user message using recent thread + recalled memory.
2. **Plan** — choose the execution shape: single-agent, pipeline, or parallel fan-out
   (delegates the *who* to the Router, owns the *how/order*).
3. **Context** — ask the Agent Context Builder for a token-budgeted context pack.
4. **Dispatch** — send each agent a typed `AgentTask` with a least-privilege scope.
5. **Gate** — route every proposed action through the Policy Engine (G/Y/R).
6. **Compose** — merge agent outputs into one reply (Personality layer shapes voice).
7. **Persist + audit** — write the assistant message, `agent_run`/`agent_steps`,
   `tool_invocations`, and any `action_approvals`; enqueue proposed memories.

### 4.3 Interfaces
```
orchestrate(session, user_id, conversation_id, message, *, history, summary,
            memories, llm, embeddings, policy, registry, router, context_builder)
   → OrchestrationResult{ reply, agent_runs[], proposed_actions[],
                          proposed_memories[], citations[], cost, message_metadata }
```
Called by `run_turn` in place of `generate_grounded_reply`; returns the same
reply-shaped payload `run_turn` already persists, so steps 6–10 of the Phase 2 turn
(append assistant message, touch lifecycle, commit, enqueue enrichment) are unchanged.

### 4.4 Data flow
`run_turn` → `orchestrate` → (Router selects agents) → Context Builder packs context →
agent handlers run (LLM + Tool Interface) → Policy gate → compose → return
`OrchestrationResult`. `run_turn` commits once (atomic with the user/assistant
messages), then the enrichment worker fires post-commit as today.

### 4.5 Database impact
Owns writes to `agent_runs` (one per orchestration) and `agent_steps` (one per agent
invocation), both flushed inside the turn's unit of work so they commit atomically with
the messages. No change to Phase 1/2 tables.

### 4.6 API impact
**None required** in the first cut — orchestration is internal to the existing
`POST /conversations/{id}/messages`. Optional later: `GET /conversations/{id}/runs` to
expose the trace to the Activity Feed (additive, read-only).

### 4.7 Service layer impact
New `app/services/agents/orchestrator_service.py`. Depends on Registry, Router, Context
Builder, Policy Engine, Agent Runtime. `conversation_turn_service` gains a one-line
branch behind `settings.agents_orchestration_enabled`; nothing in the memory or
conversation domains imports the agents domain (dependency direction preserved).

### 4.8 Risks
- **Latency creep** from multi-step routing vs. the single Phase 2 call.
- **Single point of failure** — a bug here breaks every turn; mitigated by the flag and
  a guaranteed fallback to `generate_grounded_reply` on orchestrator error.
- **Composition incoherence** when merging parallel agent outputs.

### 4.9 Tradeoffs
Centralizing routing/policy/compose in one service buys traceability, one security
choke point, and a stable contract — at the cost of the Orchestrator becoming a hot
path that must stay lean and well-instrumented. We accept it because every alternative
(per-agent routing, peer chat) sacrifices the central policy guarantee.

---

## 5. Core Component — Agent Registry

### 5.1 Purpose
The source of truth for *which agents exist*, what each can do, the tools it may call,
and its permission ceiling. Makes "add an agent" a data + handler operation.

### 5.2 Responsibilities
- Hold each agent's **manifest**: `key`, display name, mission, input/output schema ref,
  **tool manifest** (allowed tool keys), **permission ceiling** (G/Y/R), model-tier
  hint, enabled flag, and routing descriptors (keywords/intents/embeddings) the Router
  consumes.
- Validate manifests at startup (ceiling ≥ any tool's tier; tools exist in the Tool
  Interface).
- Expose lookups by `key` and enumeration of enabled agents to the Router.

### 5.3 Interfaces
```
registry.get(agent_key) → AgentManifest
registry.list_enabled(user_id) → AgentManifest[]      # per-user enablement later
registry.resolve_handler(agent_key) → AgentHandler     # the callable agent
```

### 5.4 Data flow
Loaded at app startup from **code-defined defaults** (static manifests) overlaid with a
DB `agents` table for runtime enable/disable and per-user config. Router and Orchestrator
read it; nothing writes it on the request path.

### 5.5 Database impact
New table `agents` (global catalog rows; nullable `user_id` for user-defined agents in
the far future). Phase 3 seeds built-in agents via migration. RLS: global rows readable
by all tenants (read-only), user-defined rows tenant-scoped.

### 5.6 API impact
Optional later: `GET /api/v1/agents` (list capabilities for the UI Permission Center).
Not required for Phase 3 core.

### 5.7 Service layer impact
New `app/services/agents/registry.py` + `app/repositories/agent_repository.py`.
Manifests live as typed objects (e.g. a `manifests/` module) so the static set is
reviewable in code; the DB only carries mutable flags.

### 5.8 Risks
- **Drift** between code manifests and DB rows.
- **Over-broad tool manifests** granting an agent more than it needs.

### 5.9 Tradeoffs
Code-defined manifests (reviewable, type-checked) + DB overlay (runtime toggles) is more
moving parts than pure-DB or pure-code, but gives both auditability and operability. We
favor code as the source of truth and DB as state, mirroring how Phase 2 kept logic in
services and state in tables.

---

## 6. Core Component — Agent Router

### 6.1 Purpose
Decide *which* agent(s) a parsed intent should go to, and propose the execution shape
(single / pipeline / parallel) for the Orchestrator to run.

### 6.2 Responsibilities
- Classify intent → candidate agents using a layered strategy:
  **(a)** the conversation's `agent_context` hint (already on `conversations`),
  **(b)** keyword/intent rules from manifests, **(c)** an LLM router fallback for
  ambiguous intent, optionally **(d)** embedding similarity to agent descriptors.
- Produce a `RoutingDecision{ plan_shape, steps[], rationale, confidence }`.
- Default to a single general-purpose agent when confidence is low (safe fallback).

### 6.3 Interfaces
```
router.route(intent, context_pack, registry, *, llm) → RoutingDecision
```

### 6.4 Data flow
Orchestrator → Router (reads Registry + the conversation's `agent_context`) →
`RoutingDecision` → Orchestrator executes. The decision is recorded on the `agent_run`
for observability and eval.

### 6.5 Database impact
No new table of its own; the chosen route + rationale are stored on `agent_runs`
(`route_plan` JSONB) for tracing and future router evals.

### 6.6 API impact
None.

### 6.7 Service layer impact
New `app/services/agents/router.py`. The cheap rule/keyword path runs without an LLM
call; the LLM fallback uses the existing `llm` gateway with a cheap model tier
(`claude_model_fast`, the cost-routing seam Phase 2 left open).

### 6.8 Risks
- **Misrouting** sends a request to the wrong specialist.
- **LLM-router cost/latency** on every ambiguous turn.
- **Router prompt injection** from message content steering routing.

### 6.9 Tradeoffs
A layered rules-first, LLM-last router trades some classification accuracy for low cost
and determinism on the common path, escalating to an LLM only when rules are
inconclusive. Alternative pure-LLM routing is simpler but adds a model call to every
turn — rejected on cost.

---

## 7. Core Component — Shared Agent Memory Access

### 7.1 Purpose
Give every agent a uniform, consent-respecting, tenant-isolated read/write door into the
**one** long-term memory — the shared bus through which agents exchange durable
knowledge ([agent-framework.md](../architecture/agent-framework.md) §5).

### 7.2 Responsibilities
- **Read:** scoped retrieval via `memory_retrieval_service` (hybrid pgvector + recency +
  importance), filtered to the agent's domain when appropriate.
- **Write (propose):** agents return `proposed_memories`; persistence goes through
  `memory_service.create_memory` (the Memory Engine — scoring, versioning, embedding) and
  is **consent-gated** exactly as Phase 2 extraction is (`ConsentMode`).
- **Provenance:** every agent-written memory records a `memory_sources` row; Phase 3
  widens `source_kind` from `{conversation}` to include `{agent, document, activity}`.

### 7.3 Interfaces
```
mem.recall(user_id, query, *, agent_key, filters, budget) → MemoryHit[]
mem.propose(user_id, candidates[], *, agent_key, run_id, consent) → ProposedMemory[]
```
Both delegate to existing services; no new memory logic is written.

### 7.4 Data flow
Agent → `mem.recall` (read path, Green) during reasoning; Agent → returns
`proposed_memories` → Orchestrator → consent gate → `memory_service.create_memory` +
`memory_source_repository.link_source(source_kind='agent')`.

### 7.5 Database impact
Extend the `memory_sources.source_kind` CHECK/enum to add `agent` (and reserve
`document`, `activity`). New migration alters the constraint only — no data migration,
no change to `memories`. This is the "shared provenance bus" seam Phase 2 named.

### 7.6 API impact
None (existing `/api/v1/memories/*` already exposes the Memory Center).

### 7.7 Service layer impact
Thin `app/services/agents/agent_memory.py` facade over `memory_service`,
`memory_retrieval_service`, `memory_source_repository`. **No duplication** of scoring,
versioning, embedding, or retrieval logic — the facade only adapts the agent contract to
the Memory Engine.

### 7.8 Risks
- **Cross-agent contamination** — one agent writing noise other agents recall.
- **Consent bypass** if an agent writes outside the gate (prevented by routing *all*
  writes through the Orchestrator's gate, never agent-direct).
- **Domain leakage** — an agent recalling memories outside its remit.

### 7.9 Tradeoffs
A single shared memory (vs. per-agent silos) is the moat — it's what makes agents
compound on each other. The cost is contamination risk and the need for category/domain
filtering and confidence scoring. We keep one store and lean on the Memory Engine's
existing importance/confidence to manage noise.

---

## 8. Core Component — Agent Context Builder

### 8.1 Purpose
Assemble the **token-budgeted context pack** an agent needs: relevant memories, recent
thread, rolling summary, goal/task state, and tool results — without leaking another
tenant's data and without blowing the model budget.

### 8.2 Responsibilities
- Gather: recalled memories (Shared Memory Access), recent messages + rolling summary
  (Phase 2 repositories), active goals/tasks (Goal & Task Foundation), prior agent
  outputs in this run.
- Budget + dedupe via `context_assembly_service`, then shape with `prompt_builder`.
- Produce a **scoped** pack per agent — an agent receives only what its task needs.

### 8.3 Interfaces
```
context_builder.build(user_id, conversation_id, intent, *, agent_key, budget)
   → ContextPack{ memories[], history[], summary, goals[], tasks[], scratch[] }
```

### 8.4 Data flow
Orchestrator → `build` → reuses `memory_retrieval_service` + `message_repository`
(`recent_messages`) + `conversation_summary_repository` (`latest_summary`) + the new
goals/tasks repos → `context_assembly_service` (budget) → `ContextPack`. This is the
Phase 2 context-layering (`system + history + summary + memories + query`) generalized to
add goals/tasks.

### 8.5 Database impact
Reads only; reads the new `goals`/`tasks` tables in addition to Phase 1/2 tables.

### 8.6 API impact
None.

### 8.7 Service layer impact
New `app/services/agents/context_builder.py` — a composition layer. It **wraps**
`context_assembly_service` and `prompt_builder`; it does not replace them (their token
budgeting and dedupe are reused intact).

### 8.8 Risks
- **Context bloat / cost** if budgets aren't enforced per agent.
- **Stale or irrelevant packing** hurting agent quality.
- **Over-scoping** leaking unneeded data to an agent (minimize surface).

### 8.9 Tradeoffs
A per-agent scoped pack costs extra retrieval/assembly work versus one shared blob, but
keeps prompts lean, cheaper, and least-privilege. We accept the extra assembly because
Phase 2 already proved the budgeting machinery; we're composing, not building anew.

---

## 9. Core Component — Agent-to-Agent Communication

### 9.1 Purpose
Let agents collaborate (pipeline hand-offs, fan-out/gather) **safely** — structured,
orchestrated, audited — never free-form peer chat.

### 9.2 Responsibilities
- Define the **typed task/result contract** (the heart of the framework):
  ```
  AgentTask   { run_id, agent_key, intent, inputs, context_pack, permission_scope }
  AgentResult { output, proposed_actions[], proposed_memories[], citations[],
                cost{tokens,usd}, next_suggestions[] }
  ```
- Route all inter-agent data **through the Orchestrator** (no side channels in Phase 3);
  the durable bus is **shared memory**, not giant payload passing.
- Persist each hop as an `agent_messages` row for full traceability.

### 9.3 Interfaces
```
handler(task: AgentTask, *, tools, mem, llm) → AgentResult     # every agent implements
orchestrator passes AgentResult.output of step N → inputs of step N+1 (pipeline)
```

### 9.4 Data flow
Orchestrator → `AgentTask` → handler → `AgentResult` → (compose | feed next agent).
Pipeline = sequential hand-off; parallel = fan-out then gather/merge;
human-in-the-loop = propose → Policy gate → (later) Action Agent executes.

### 9.5 Database impact
New `agent_messages` table: `run_id`, `from_agent`, `to_agent` (nullable = orchestrator),
`role`, `payload` JSONB, `seq`, `user_id`, timestamps — the inter-agent audit trail. Also
modeled on the existing `messages.role='tool'` + `messages.metadata` seam so tool/agent
turns can surface in the conversation thread when useful.

### 9.6 API impact
None in Phase 3 (internal). Future Activity-Feed read endpoint may surface the trace.

### 9.7 Service layer impact
The contract types live in `app/schemas/agents.py`; the relay logic lives in the
Orchestrator. Agent handlers are pure `AgentTask → AgentResult` functions in
`app/services/agents/handlers/`.

### 9.8 Risks
- **Cascade failures / loops** in pipelines (A→B→A).
- **Cost blowups** from chained LLM calls (runaway-loop guard required).
- **Latency stacking** in long pipelines.

### 9.9 Tradeoffs
Orchestrator-mediated communication (vs. direct peer-to-peer) costs a hop and some
latency but buys traceability, loop guards, and one security boundary — exactly why the
framework forbids side channels early. Scoped, supervised sub-graphs (LangGraph) are the
later evolution once the contract is proven (§14).

---

## 10. Core Component — Tool Execution Interface

### 10.1 Purpose
A single, typed, policy-gated door through which agents call tools (web search, browser,
files, email, calendar, DB) — so capability is centralized, audited, and least-privilege.

### 10.2 Responsibilities
- Maintain a **tool catalog**: each tool has a `key`, typed input/output schema, a
  **permission tier** (G/Y/R), and an idempotency/retry policy.
- Enforce the **manifest check** (the agent's manifest must list the tool) **and** the
  **policy gate** (the tool's tier vs. user settings/standing allowances) before any
  execution.
- Treat all external tool output as **untrusted** (no permission escalation via content).
- Record every call as a `tool_invocations` row (args, tier, decision, outcome, cost).

### 10.3 Interfaces
```
tools.invoke(tool_key, args, *, agent_key, run_id, policy, user_id)
   → ToolResult{ output, status, tier, approval_ref?, cost }
   # raises/blocks if tool not in agent manifest, or policy says block,
   # or returns a pending-approval handle if policy says prompt (Yellow/Red)
```

### 10.4 Data flow
Agent → `tools.invoke` → manifest check → Policy gate → (Green: run now) /
(Yellow/Red: create `action_approvals` row, return pending) → execute on approval →
`tool_invocations` row + audit. Red execution is funneled to the **Action Agent** (the
single audited choke point) per the framework.

### 10.5 Database impact
New `tool_invocations` (audit of every call) and `action_approvals` (pending/approved
Yellow/Red actions with preview, decision, expiry). Both `user_id`-scoped, fail-closed
RLS, `gummy_app` grant. Append-only audit semantics (§ security-system §7).

### 10.6 API impact
Future (not Phase 3 core): `POST /api/v1/actions/{id}/approve|reject` and
`GET /api/v1/actions` to power the Permission Center / confirm-before-acting UI. Phase 3
ships the data model and the gate; the approval UI is a later milestone.

### 10.7 Service layer impact
New `app/services/agents/tools/` with a `ToolInterface` protocol and a registry of tool
adapters; new `app/services/agents/policy_engine.py` (the G/Y/R evaluator). Phase 3
implements **Green (read-only) tools only** (web search, memory read, document read);
Yellow/Red tools are *modeled and gated* but their executors are stubbed/deferred so no
risky action can fire before the approval UI exists.

### 10.8 Risks
- **Over-permissioned tools** or a manifest bug granting too much.
- **Prompt-injection** trying to trigger a tool the user didn't intend.
- **Unbounded/expensive tool loops.**

### 10.9 Tradeoffs
One central gated interface (vs. agents calling SDKs directly) adds an indirection layer
but is the only way to guarantee the manifest+policy invariant and a complete audit
trail. Shipping Green-only first trades capability breadth for safety — we refuse to wire
executors for Red actions before the human-in-the-loop UI is real.

---

## 11. Core Component — Goal & Task Foundation

### 11.1 Purpose
The persistent backbone that turns chat into *sustained, multi-session work*: durable
**goals** (what the user wants) decomposed into **tasks** (units of agent work with
status) — the substrate the GSD Framework and Multi-Agent Workforce (§14) build on.

### 11.2 Responsibilities
- Model **goals** (`title`, `description`, `status{active,paused,done,abandoned}`,
  `agent_context`, target date, priority) and **tasks** (`goal_id?`, `agent_key?`,
  `title`, `status{pending,in_progress,blocked,done,cancelled}`, `result_ref`, ordering).
- Let the Orchestrator create/advance tasks as a side effect of a turn, and let the
  Context Builder surface active goals/tasks into the context pack.
- Provide the join point between a conversation, a memory, and ongoing work
  (provenance: a task can reference the `agent_run` that produced it).

### 11.3 Interfaces
```
goal_service.create / list / update / complete(...)
task_service.create / advance / block / complete(... , agent_key, goal_id?)
```

### 11.4 Data flow
Orchestrator (or, later, a proactive scheduler) creates/advances goals/tasks within the
turn's unit of work; Context Builder reads active items into packs; the Activity Feed
(future) renders progress. Completed tasks may emit `proposed_memories` (durable
outcomes).

### 11.5 Database impact
New `goals` and `tasks` tables (migrations `0012`+), `user_id`-scoped, fail-closed RLS,
`gummy_app` grant, string-backed enums with CHECK constraints — Phase 2 conventions
exactly. `tasks.agent_run_id` (nullable FK → `agent_runs`) ties work to its producing
run; `ON DELETE SET NULL` so durable goals survive run cleanup.

### 11.6 API impact
Future: `GET/POST/PATCH /api/v1/goals` and `/api/v1/tasks` to power a goals/tasks UI.
Not required for the Phase 3 framework core (the Orchestrator can manage them
internally), but the tables are designed for it.

### 11.7 Service layer impact
New `app/services/agents/goal_service.py`, `task_service.py` +
`app/repositories/goal_repository.py`, `task_repository.py` (flush-only). Services own
the commit boundary; repos are pure persistence.

### 11.8 Risks
- **Scope creep** — goals/tasks becoming a full project-management product prematurely.
- **Orphaned/stale tasks** never closed.
- **Status-model churn** as real agents reveal needed states.

### 11.9 Tradeoffs
Introducing goals/tasks now (before any agent strictly needs them) costs two tables and
risks YAGNI, but every domain agent and the GSD/Workforce vision needs durable work
state — building it into the framework avoids a later cross-cutting retrofit. We keep the
schema deliberately minimal (status + ordering + provenance) and let agents drive its
evolution.

---

## 12. Agent lifecycle

Generalizes [agent-framework.md](../architecture/agent-framework.md) §8 onto the Phase 2
machinery:

```
Register → Receive AgentTask → Load ContextPack → Reason (LLM + gated tools)
        → Propose actions/memories → (Policy gate: allow | prompt | block)
        → Return AgentResult → Orchestrator composes → Persist + audit → Idle
```

1. **Register** (startup) — manifest validated into the Registry (role, tools, ceiling,
   model tier).
2. **Invoke** — Orchestrator dispatches a typed `AgentTask` with a scoped pack.
3. **Reason** — handler calls the LLM (tier per task) and only manifest-listed tools via
   the Tool Interface.
4. **Propose** — returns `AgentResult` with outputs + proposed actions/memories (never
   executed by the agent itself).
5. **Gate** — Policy Engine applies Green/Yellow/Red against user settings + ceiling.
6. **Compose & persist** — Orchestrator merges, writes `agent_run`/`agent_steps`/
   `tool_invocations`, enqueues consent-gated memories, appends the assistant message —
   all inside `run_turn`'s single commit.
7. **Observe** — every run is traced + cost-tracked (`agent_runs.cost_*`,
   `agent_steps`), ready for Langfuse-style observability.
8. **Idle/retire** — stateless; all durable state is in memory/DB, so agents scale
   horizontally.

**Failure handling:** an agent or tool failure is isolated (recorded on its
`agent_step`), and the Orchestrator either falls back to a simpler plan or, in the worst
case, to `generate_grounded_reply` — the user always gets a reply.

---

## 13. Strategies

### 13.1 Shared memory strategy
- **One store, many agents.** All agents read/write the single Phase 1 Memory Engine via
  the Shared Memory Access facade — no per-agent memory silos. This is the compounding
  moat: the Career Agent benefits from what the Research Agent learned.
- **Read = Green, write = consent-gated.** Recall is free and logged; writes go through
  `memory_service.create_memory` under `ConsentMode` (autonomous saves; assisted/explicit
  propose — the same gate Phase 2 ships).
- **Provenance for every write.** `memory_sources.source_kind` widens to `agent`, so the
  Memory Center stays a complete, user-owned "where did this come from" view across
  conversations *and* agent activity.
- **Domain scoping, not domain ownership.** Agents *filter* recall by category/domain for
  relevance, but no agent "owns" a memory — the user does. Importance/confidence scoring
  (existing) manages cross-agent noise.
- **No training on user memory** (security-system §4) — isolation preserved.

### 13.2 Agent communication strategy
- **Structured, never free-form.** All coordination is the typed `AgentTask`/`AgentResult`
  contract; there is no natural-language agent gossip.
- **Orchestrator-mediated in Phase 3.** No peer-to-peer side channels — every hop is
  visible, audited (`agent_messages`), loop-guarded, and cost-capped.
- **Memory is the durable bus.** Big durable knowledge is exchanged by writing/reading
  memory, not by passing giant payloads between agents.
- **Four coordination patterns:** single-agent · pipeline · parallel fan-out/gather ·
  human-in-the-loop (propose → confirm → act).
- **Evolution path:** supervised LangGraph sub-graphs later enable *scoped, audited*
  agent-to-agent delegation — without removing the central policy guarantee (§14).

---

## 14. Future compatibility

Each future capability is checked against the Phase 3 contract to prove **no framework
change** is needed to add it — that is the whole point of building the framework first.

### 14.1 Domain agents (Career · Learning · Fitness · Marketing · Research · Business)
All six are **handlers + manifests + (optional) domain tables** — pluggable, no
framework change:

| Agent | New domain table(s) (later) | Tools used | Ceiling | Notable |
| --- | --- | --- | --- | --- |
| 💼 **Career** | `jobs`, `applications` | web/browser (Y), files (Y) | 🟡 | resume tailoring from Profile/Doc memory; submit = per-application confirm |
| 📚 **Learning** | `learning_plans`, `progress` | web (G), files (G) | 🟡 | spaced repetition; consumes Research outputs |
| 💪 **Fitness** | `health_*` (sensitive) | vision (G), daily-life (Y) | 🔴 | **Health Memory** is Red-sensitive: explicit consent, never auto-saved, extra encryption, medical disclaimers |
| 📈 **Marketing** | `campaigns` | research (G), social (R) | 🔴 | publish/ad-spend = Red; brand-voice via Personality memory |
| 🔬 **Research** | `research_reports` | web search (G), browser (Y) | 🟢 (read) | first LangGraph candidate (multi-step, branching) |
| 🏢 **Business** | `org_*` (Phase 14) | broad, org-scoped | mixed | needs `organization_id` tenancy extension |

**Why each fits unchanged:** they implement `AgentTask → AgentResult`, declare a tool
manifest + ceiling in the Registry, read/write the shared memory through the facade,
route risky actions through the Policy Engine → Action Agent, and decompose work into
`goals`/`tasks`. The only *additive* work is domain tables (their own migrations) and
handlers — never a change to the Orchestrator, Router, or contract.

**Business Agent caveat:** it is the one future agent needing a **tenancy extension** —
adding `organization_id` alongside `user_id` and org-scoped RLS policies (Phase 14). The
Phase 3 tables are designed to accept an additive `organization_id` column without
reshaping (multi-tenant-from-day-one principle).

### 14.2 Workflow Learning System
**Concept:** observe repeated agent pipelines a user runs and *learn* reusable workflows
(promote an ad-hoc pipeline into a named, reusable plan).
**Fit:** the substrate already exists — `agent_runs` + `agent_steps` + `route_plan` are a
complete, queryable history of every orchestration. A future learner mines that history,
proposes a saved workflow (stored as a `goals`/`tasks` template + a fixed `route_plan`),
and the Router gains a "known-workflow" lookup layer. **No contract change** — it's a new
consumer of existing trace tables + a Router strategy.

### 14.3 GSD ("Get Stuff Done") Framework
**Concept:** the autonomous, proactive execution layer — Gummy advancing goals across
sessions without being asked each step.
**Fit:** sits directly on the **Goal & Task Foundation** (§11). A scheduler (a new
worker, modeled on `enrichment_worker`) wakes, finds `active` goals with `pending` tasks,
and dispatches them through the *same* Orchestrator path used by a live turn. Because the
Orchestrator is the single entrypoint and agents are stateless, "proactive" vs.
"reactive" is just *who triggered the task* — the execution, gating, and persistence are
identical. Red/Yellow actions still require human approval, so autonomy never bypasses
consent.

### 14.4 Multi-Agent Workforce
**Concept:** supervised teams of agents tackling big jobs ("research → outline → build →
review") with concurrency at scale.
**Fit:** the long-horizon evolution of §9 — supervisor + worker sub-graphs via
**LangGraph**, adopted *per-workflow* (starting with deep research), not as a rewrite.
Because agents already share one contract and the Orchestrator owns routing, adopting
LangGraph means re-expressing *orchestration logic* as a graph — **agents don't change**.
Concurrency rides the existing worker/queue tier (today in-process asyncio; a shared
queue when horizontal scale-out is needed). Scoped, audited agent-to-agent delegation
becomes possible *inside* a supervised sub-graph while the central policy guarantee
holds.

### 14.5 Future roadmap integration
- **Phase 4+ domain agents** plug in as handlers (§14.1) — the framework is their
  precondition.
- **Personality layer** (roadmap Phase 8) is the compose-time voice shaper the
  Orchestrator already calls last.
- **Vision/Video** agents are read-tools feeding context packs and proposing memories —
  same contract.
- **Voice/Mobile** are new *clients* of the same `run_turn`/Orchestrator path — no agent
  changes.
- **Business Automation (Phase 14)** is the `organization_id` tenancy extension + org
  agents + the agent marketplace (third-party agents conforming to the contract, running
  inside the permission model).

---

## 15. Migration roadmap

Phase 3 ships incrementally behind a flag; the Phase 2 turn stays the default until each
milestone is proven. Migrations continue from head `0011` (so `0012`+). No existing
table is reshaped; every change is additive.

| Milestone | Deliverable | Migration(s) | Flag-gated? |
| --- | --- | --- | --- |
| **M1 — Contract & Registry** | `AgentTask`/`AgentResult` schemas, `AgentManifest`, in-code Registry, `agents` table seeded with built-ins. No routing yet. | `0012_add_agents` | n/a (inert) |
| **M2 — Run recording** | `agent_runs` + `agent_steps` tables + recorder service. `run_turn` writes a single-agent "general" run that wraps today's `generate_grounded_reply` — **behavior identical**, now traced. | `0013_add_agent_runs` | `agents_run_recording` |
| **M3 — Orchestrator (single-agent)** | Orchestrator + Context Builder wrapping Phase 2 services; one general-purpose agent handler. `run_turn` delegates behind flag; guaranteed fallback to `generate_grounded_reply`. Parity tests vs. Phase 2. | — | `agents_orchestration_enabled` |
| **M4 — Router + 2nd agent** | Router (rules→LLM fallback) + a second trivial specialist (e.g. a read-only "Research/Recall" agent) to prove routing + pipeline. | — | flag |
| **M5 — Tool Interface (Green only)** | `ToolInterface`, Policy Engine (G/Y/R), `tool_invocations` table, web-search + memory-read + doc-read tools. Yellow/Red **modeled + gated but executors deferred**. | `0014_add_tool_invocations` | flag |
| **M6 — Shared memory writes + provenance** | Agent-proposed memories via consent gate; widen `memory_sources.source_kind` to `agent`. | `0015_widen_source_kind` | flag |
| **M7 — Goal & Task Foundation** | `goals` + `tasks` tables, services, Context-Builder surfacing; Orchestrator can create/advance tasks. | `0016_add_goals_tasks` | flag |
| **M8 — A2A trace + compose** | `agent_messages` table; parallel fan-out/gather + compose; Personality-shaped compose hook. | `0017_add_agent_messages` | flag |
| **M9 — Approvals data model + action_approvals** | `action_approvals` table + Policy-gate "prompt" path returning pending handles (UI deferred). Wires the human-in-the-loop seam without firing any Red action. | `0018_add_action_approvals` | flag |
| **M10 — Seal** | Flip `agents_orchestration_enabled` on by default once parity + evals pass; keep `generate_grounded_reply` as the fallback core. As-implemented `PHASE3_ARCHITECTURE.md`. | — | default-on |

**Rollback posture:** every milestone is reversible by clearing its flag; the Phase 2
path (`generate_grounded_reply`) is never deleted — it becomes the orchestrator's
single-agent fallback, exactly as Phase 2 kept it after retiring `/chat`.

**Deferred to Phase 4+ (not Phase 3):** rich domain agents (Career/Learning/etc.),
Yellow/Red tool *executors*, the approval UI, LangGraph sub-graphs, the GSD scheduler,
and the Workflow Learning miner. Phase 3's job is the **framework + trace tables + Green
path**, proven by trivial agents.

---

## 16. Testing strategy

Mirrors Phase 2's hermetic-first, live-verified approach.

- **Hermetic unit/integration (SQLite, no worker, fake providers).** The default suite:
  `fake_provider` LLM + embeddings, dev-bypass tenancy via `?user_id=`. Covers Registry
  validation, Router decisions (deterministic rules path), Context Builder budgeting,
  contract serialization, Orchestrator compose, and Goal/Task state transitions.
- **Parity tests (the critical gate).** With `agents_orchestration_enabled` on, a
  single-agent route through the Orchestrator must produce a reply **equivalent** to
  `generate_grounded_reply` for the same input — proving M3 is behavior-preserving before
  default-on (M10).
- **Policy-engine tests.** Exhaustive Green/Yellow/Red matrix: manifest check, ceiling
  enforcement, standing allowances, "no always-allow for Red," and the prompt-injection
  invariant (external tool content cannot escalate tier or approve an action).
- **RLS / tenant-isolation tests (live Postgres, gated).** Extend `test_rls_postgres.py`
  to every new table (`agents` user-rows, `agent_runs`, `agent_steps`, `agent_messages`,
  `goals`, `tasks`, `tool_invocations`, `action_approvals`): per-tenant isolation,
  fail-closed (unset GUC → zero rows), and `WITH CHECK` rejection under `gummy_app`.
- **Router quality evals.** A labeled intent→agent fixture set scored for routing
  accuracy and misroute rate; run as an eval (not a hard pass/fail unit test) so the
  router can improve without flaking CI. Cost/latency budget assertions on the LLM-router
  fallback.
- **Loop/cost-guard tests.** Force a pipeline cycle and a runaway tool loop; assert the
  guard halts within the configured step/cost cap and records the failure on the
  `agent_run`.
- **Failure-isolation tests.** A failing agent/tool must isolate to its `agent_step` and
  trigger the Orchestrator fallback so the user still gets a reply (the Phase 2 worker
  "isolate + continue" discipline, applied to the request path).
- **Migration tests.** Each `0012`–`0018` upgrades and downgrades cleanly on SQLite and
  Postgres; `source_kind` widening preserves existing `conversation` rows; short Alembic
  revision ids (≤ VARCHAR(32), per Phase 2's lesson).
- **Compile-only SQL helpers.** Postgres-only queries (any new pgvector/FTS routing
  helpers) ship `build_*_statement` pure functions that compile-test on SQLite, executed
  live only under the gated Postgres suite — the Phase 2 pattern.

---

## 17. Consolidated impact summary

**New tables (all `user_id`-scoped, fail-closed RLS, `gummy_app`-granted, string enums +
CHECK):** `agents`, `agent_runs`, `agent_steps`, `agent_messages`, `goals`, `tasks`,
`tool_invocations`, `action_approvals`.
**Altered (additive only):** `memory_sources.source_kind` += `agent` (reserve `document`,
`activity`).
**Untouched:** all Phase 1 memory tables, all Phase 2 conversation tables, auth, RLS GUC
mechanism, both existing workers.

**New services (`app/services/agents/`):** `orchestrator_service`, `registry`, `router`,
`context_builder`, `agent_memory` (facade), `policy_engine`, `goal_service`,
`task_service`, `tools/` (interface + Green adapters), `handlers/` (agent handlers),
`run_recorder`.
**New repositories:** `agent_repository`, `agent_run_repository`,
`agent_message_repository`, `goal_repository`, `task_repository`,
`tool_invocation_repository`, `action_approval_repository` (all flush-only).
**New schemas (`app/schemas/agents.py`):** `AgentTask`, `AgentResult`, `AgentManifest`,
`ContextPack`, `RoutingDecision`, `OrchestrationResult`.
**New worker (later, GSD):** a proactive scheduler modeled on `enrichment_worker`.
**Touched existing code:** one flag-gated branch in `conversation_turn_service.run_turn`
delegating to the Orchestrator, with `generate_grounded_reply` retained as fallback.
Nothing in the memory or conversation domains imports the agents domain (acyclic
dependency direction preserved).

---

## 18. Top risks & mitigations (rollup)

| Risk | Mitigation |
| --- | --- |
| Orchestrator becomes a fragile hot path / SPOF | Feature flag + guaranteed `generate_grounded_reply` fallback; parity tests before default-on |
| Latency/cost from multi-step routing | Rules-first router; cheap model tier for LLM fallback; per-run step + cost caps |
| Misrouting to wrong agent | Layered router + low-confidence → general-agent default; routing evals |
| Cross-agent memory contamination | Single store + domain-filtered recall + Memory-Engine importance/confidence; consent gate on all writes |
| Risky action fires before UI exists | Green-only executors in Phase 3; Yellow/Red modeled + gated but executors deferred; Red funneled to a single Action Agent choke point |
| Prompt injection via tool output | External content is untrusted data; cannot escalate tier or approve actions; Red always needs human approval |
| Runaway pipelines / loops | Loop guards, step/cost caps, failure isolation per `agent_step` |
| Tenant data leakage on new tables | Denormalized `user_id` + fail-closed direct-column RLS + live `gummy_app` isolation tests on every table |
| Goal/Task scope creep | Minimal status+ordering+provenance schema; let real agents drive evolution |
| Schema churn as agents mature | Everything additive + flag-gated + reversible; no Phase 1/2 reshaping |

---

_Related: [../architecture/agent-framework.md](../architecture/agent-framework.md) ·
[../architecture/system-design.md](../architecture/system-design.md) ·
[../architecture/security-system.md](../architecture/security-system.md) ·
[../architecture/memory-system.md](../architecture/memory-system.md) ·
[PHASE2_ARCHITECTURE.md](PHASE2_ARCHITECTURE.md) (the machinery this builds on) ·
[ROADMAP.md](ROADMAP.md) · [FUTURE_AGENTS.md](FUTURE_AGENTS.md)._
