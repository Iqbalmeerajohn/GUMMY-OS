# GUMMY OS — Phase 3 Architecture (as implemented)

The **Agent Framework / Master Orchestrator** as actually built across
milestones M1–M11 (tag `phase3-complete`). This describes the shipped code;
where the implementation deviated from [PHASE3_PLAN.md](PHASE3_PLAN.md) /
[PHASE3_PROGRESS_PLAN.md](PHASE3_PROGRESS_PLAN.md) it is called out.
Migration head: `0018_add_action_approvals`. Suite: `348 passed, 4 skipped`
(SQLite) + 4 Postgres-gated isolation tests.

---

## 1. System overview

Phase 3 turns the single-pipeline chat turn into a **routed, traced,
policy-gated multi-agent orchestration** — without changing what the user
sees: parity with the Phase 2 reply core was the gate at every step, and
that core remains the permanent fallback.

```
   Client ── Bearer JWT ──▶ POST /api/v1/conversations/{id}/messages
                                  │ get_current_user → tenant ContextVar (unchanged)
                                  ▼
                   conversation_turn_service.run_turn        ← Phase 2 entrypoint
                                  │ agents_orchestration_enabled (DEFAULT ON, M11)
              ┌───────────────────┼──────────────────────────────┐
              │ on error: guaranteed fallback                     │
              ▼                                                   ▼
   generate_grounded_reply                 ┌──── MASTER ORCHESTRATOR ────────────┐
   (legacy core, never deleted)            │ route → context pack → execute plan │
                                           │ → compose → trace → reply payload   │
                                           └──┬──────┬──────┬──────┬──────┬──────┘
                                              ▼      ▼      ▼      ▼      ▼
                                          Registry Router Context Policy  Run/A2A
                                          (+seed)  (rules  Builder Engine  Recorder
                                                   →LLM)   (M8 g/t) (G/Y/R)
                                              │      │       │       │       │
                                              ▼      ▼       ▼       ▼       ▼
                                          handlers/ (general · recall) · tools/
                                          (pure AgentTask → AgentResult)  (gated)
                                              │
              ┌──────── Reused, unchanged ────┴──────────────────────────────┐
              │ memory_service · memory_retrieval · context_assembly ·        │
              │ prompt_builder · embeddings · LLM gateway · enrichment_worker │
              └───────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
   PostgreSQL (gummy_app, NOBYPASSRLS) — Phase 1/2 tables + Phase 3:
   agents · agent_runs · agent_steps · agent_messages · tool_invocations ·
   goals · tasks · action_approvals     (all: user_id + fail-closed RLS + grant)
```

**Layering rule (unchanged):** HTTP thin → services own logic + the unit of
work → repositories flush-only → workers off the request path. The
Orchestrator, Registry, Router, Policy Engine, and the goal/task/approval
services are services; every new table has a flush-only repository.

---

## 2. The orchestrated turn

```
1. run_turn loads history + rolling summary (BEFORE appending the user
   message — Phase 2 ordering), appends the user message.
2. orchestrate():
   a. Router classifies the intent:
        agent_context hint → manifest keyword rules → (opt-in) LLM
        classifier on claude_model_fast → default single `general`.
   b. open_run: one agent_runs row carrying the route_plan
      (shape/steps/rationale/confidence).
   c. Context Builder packs: ranked memory candidates (hybrid retrieval,
      unchanged), caller-supplied history/summary, active goals + open
      tasks (M8), pipeline scratch.
   d. Execute the plan under the run guard (step cap 8, cost cap 60k tok):
        single/pipeline — steps in order; each step's output enters the
          next step's scratch; a step failure aborts (fallback fires).
        parallel — pure handlers fan out via asyncio.gather (DB writes stay
          sequential); a failed branch is isolated; all-failed aborts.
      Every dispatch = one agent_steps row + agent_messages hops
      (task / result / error), seq-ordered.
   e. compose: terminal reply (single/pipeline) or deterministic labeled
      merge (parallel); the Personality `shape_voice` hook is applied last
      (identity in Phase 3 — parity depends on it; guarded by test).
   f. close_run (status + accumulated cost) — all flush-only.
3. run_turn persists the assistant message, bumps lifecycle, commits ONCE —
   messages + run + steps + hops + tool audit land atomically.
4. Post-commit: enrichment worker enqueued (unchanged) and agent-proposed
   memories persisted via the consent gate (M7, best-effort).
5. Any orchestrator error → generate_grounded_reply fallback: the user
   always gets a reply (the failed run trace still commits with the turn).
```

---

## 3. Components as built

### Registry (`services/agents/registry.py`, M3)
In-code manifests ([manifests.py](../backend/app/services/agents/manifests.py))
are the source of truth; the `agents` table is the runtime overlay
(`enabled`). Validated at construction: duplicate keys, unknown tools, and
ceilings below a declared tool's tier are rejected (against the real M6
catalog). Seeded idempotently at lifespan **with no tenant GUC** — the
`agents_global_seed` RLS path; `enabled` survives reseeding.

Built-ins: **general** (Green, no tools — wraps the Phase 2
assemble→prompt→LLM core verbatim) and **recall** (Green, `memory_read`
manifest; deterministic LLM-free digest of the pack's memory candidates).

### Router (`services/agents/router.py`, M5)
Layered, rules-first: (a) `agent_context == research` → recall→general
pipeline; (b) manifest keyword match → recall pipeline; (c) LLM classifier
fallback on `claude_model_fast` (≤8 output tokens, parse-safe, failure →
default) — **opt-in via `agents_router_llm_fallback` (default off)**, a
deliberate deviation: with two agents and `general` as a safe catch-all, an
LLM call per non-keyword turn violates the plan's own cost rationale (§6.9);
(d) low-confidence default to single `general`. Decision recorded on
`agent_runs.route_plan`. Routing eval: 12 labeled intents, 12/12, floor 0.8.

### Context Builder (`services/agents/context_builder.py`, M4+M8)
Composition only: hybrid retrieval candidates (content/category/score),
history/summary passed by `run_turn` (so the current message never leaks
into history), active goals + open tasks (caps 5/10), scratch. Token
budgeting stays in `context_assembly_service`, applied by the handler at
prompt time — given identical inputs the general agent's prompt is
byte-identical to the legacy core's (the parity mechanism). Goals/tasks are
pack **data**; no Phase 3 handler renders them into a prompt.

### Policy Engine (`services/agents/policy_engine.py`, M6)
A pure function of **trusted state only** — code-defined manifest,
code-defined catalog tier, user standing allowances. Manifest check →
ceiling check → Green ALLOW · Yellow ALLOW-with-allowance-else-PROMPT ·
**Red always PROMPT** (allowances ignored). Args/tool outputs are not inputs
to the gate: prompt-injection cannot escalate, by construction (tested
structurally and behaviorally).

### Tool Execution Interface (`services/agents/tools/`, M6)
One gated door (`interface.invoke`): catalog lookup (unknown → blocked at
Red tier) → manifest check → policy gate → Green executes / prompted calls
create a **pending `action_approvals` handle** (M10) / violations blocked —
and **every path writes one `tool_invocations` audit row** (args, tier,
decision, reason, output preview, cost). Green tools: `memory_read` (real,
Phase 1 retrieval), `web_search` (offline-safe null provider behind a
swap-in seam; results flagged untrusted), `doc_read` (modeled; store is a
later phase). `email_send` (Yellow) and `social_publish` (Red) are modeled
with **no executor anywhere** — nothing risky can fire in Phase 3.

### Run/A2A Recorder (`services/agents/run_recorder.py`, M3+M5+M9)
Flush-only trace primitives: open/close runs and steps (status, error,
output, per-step + accumulated cost) plus seq-ordered `agent_messages` hops
for every task hand-off, result, and error. The standalone M3 recording mode
(`agents_run_recording`, default off) wraps the legacy call when
orchestration is disabled — byte-identical behavior, now traced.

### Goal & Task Foundation (M8)
`goals` + `tasks` with guarded transitions (terminal states final → 409),
goal-ownership enforcement on linking, run provenance
(`tasks.agent_run_id`), `flush_only=True` service variants for in-turn use,
and tenant-scoped `GET/POST/PATCH /api/v1/goals` and `/api/v1/tasks`.

### Approvals (M10)
The prompt path's pending handle: previewed `action_approvals` row (24h
TTL), decided exactly once via `POST /api/v1/actions/{id}/approve|reject`
(409 on re-decide; expired rows flip to `expired` and are never decidable).
**Approving records a decision — no executor exists**, so no side effect can
fire before the approval UI + Action Agent phase.

### Shared agent memory (M7)
`agent_memory` facade: `recall` = hybrid retrieval; `propose` = the exact
Phase 2 consent gate (`autonomous` saves; `assisted`/`explicit` persist
nothing) → `memory_service.create_memory` (scoring/versioning/embedding
unchanged) + `memory_sources.source_kind='agent'`. **Deviation:** proposals
persist **post-commit in `run_turn`** (best-effort), not inside
`orchestrate` — `memory_service` owns its own commit, and committing
mid-orchestration would break the turn's atomicity/parity.

---

## 4. Schema (migrations 0012–0018)

| Migration | Tables / change | RLS |
| --- | --- | --- |
| `0012_add_agents` | `agents` registry catalog | **3 policies**: global rows tenant-readable; writable only with no GUC (seed path); user rows standard fail-closed |
| `0013_add_agent_runs` | `agent_runs` + `agent_steps` (UNIQUE(run_id,seq)) | standard fail-closed |
| `0014_add_agent_messages` | `agent_messages` A2A trail (UNIQUE(run_id,seq)) | standard fail-closed |
| `0015_add_tool_invocations` | `tool_invocations` append-only audit | standard fail-closed |
| `0016_widen_source_kind` | `memory_sources.source_kind` CHECK → +`agent` (+reserved `document`,`activity`) | n/a (constraint only) |
| `0017_add_goals_tasks` | `goals` + `tasks` (SET NULL goal/run FKs) | standard fail-closed |
| `0018_add_action_approvals` | `action_approvals` (SET NULL run FK, expiry) | standard fail-closed |

Every table: denormalized `user_id`, RLS enabled in the creating migration
(no unprotected window), the identical fail-closed GUC predicate, a
conditional `gummy_app` grant, string enums + named CHECKs. All migrations
have verified live down/up cycles. `agent_runs.conversation_id` is SET NULL
so the audit/cost trail survives thread deletion.

---

## 5. Flags & rollback posture

| Flag | Default | Meaning |
| --- | --- | --- |
| `agents_orchestration_enabled` | **true** (since M11) | One env var reverts every turn to the verified Phase 2 path |
| `agents_run_recording` | false | Trace-only mode for the legacy path (subordinate to orchestration) |
| `agents_router_llm_fallback` | false | Opt-in LLM router classifier on the cheap tier |

The legacy reply core is never deleted: it is the orchestrator's guaranteed
in-request fallback **and** the one-toggle rollback for the entire phase.

---

## 6. Security invariants (proven by tests)

1. Fail-closed tenant isolation on all 8 new tables, live-verified under the
   non-bypass `gummy_app` role (isolation, unset-GUC zero rows, WITH-CHECK
   rejection).
2. Global agent catalog rows are tenant-readable but writable **only**
   outside a tenant transaction (the seed path) — proven live.
3. The policy gate sees only trusted state; Red never has always-allow; a
   standing allowance never approves Red.
4. No non-Green executor exists — approving an action cannot fire a side
   effect; prompted calls produce audited pending handles only.
5. External tool output is data (`untrusted: true`), never an input to the
   gate.
6. Every tool call, agent dispatch, and inter-agent hop is an audited,
   tenant-scoped row.

---

## 7. Deviations from the plan (all documented in PHASE3_PROGRESS.md)

1. **Router LLM fallback opt-in** (M5) — cost rationale; the roadmap's
   mechanism exists, the default differs.
2. **Agent memory proposals persist post-commit** (M7) — `memory_service`
   commits its own unit of work; in-orchestration persistence would break
   turn atomicity.
3. **`agents` three-policy RLS** (M1) — the roadmap's "global rows read-only
   to tenants" required splitting read/tenant/seed policies.
4. **Parallel shape is not yet router-emitted** (M9) — the machinery is
   built, traced, and tested; routes that fan out arrive with the domain
   agents that need them.

## 8. Phase 4+ seams left open

Domain agents = manifest + handler + entry in `handlers.dispatch` (no
framework change). Yellow/Red executors + the Action Agent hang off the
approval decision. The GSD scheduler is a worker dispatching
`trigger='scheduler'` runs through the same `orchestrate`. Workflow learning
mines `agent_runs.route_plan` + `agent_steps`. LangGraph sub-graphs replace
orchestration internals per-workflow without touching the agent contract.

---

_Related: [PHASE3_PLAN.md](PHASE3_PLAN.md) ·
[PHASE3_PROGRESS_PLAN.md](PHASE3_PROGRESS_PLAN.md) ·
[PHASE3_PROGRESS.md](PHASE3_PROGRESS.md) ·
[PHASE2_ARCHITECTURE.md](PHASE2_ARCHITECTURE.md)._
