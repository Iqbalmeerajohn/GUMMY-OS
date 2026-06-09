# GUMMY OS — Phase 3 Implementation Roadmap (Agent Framework / Master Orchestrator)

Implementation plan of record for Phase 3. Design of record:
[PHASE3_PLAN.md](PHASE3_PLAN.md). This doc sequences the build into milestones —
ordered **lowest risk → highest risk** — each following the same
**schema → repositories → services → APIs → verification** discipline proven in
[PHASE1_5_PLAN.md](PHASE1_5_PLAN.md) and [PHASE2_PROGRESS.md](PHASE2_PROGRESS.md).

> **Status:** Planning / design for review. **No implementation yet.**
> **Baseline:** tag `phase2-complete`, migration head `0011_extraction_watermark`,
> suite `203 passed, 3 skipped` (SQLite) + 3 Postgres-gated isolation tests.
> **Companion docs:** [PHASE3_PLAN.md](PHASE3_PLAN.md),
> [PHASE2_ARCHITECTURE.md](PHASE2_ARCHITECTURE.md),
> [../architecture/agent-framework.md](../architecture/agent-framework.md),
> [../architecture/security-system.md](../architecture/security-system.md).

---

## Guiding principles (carried over, unchanged)

1. **Additive only.** No Phase 1/1.5/2 table, service, endpoint, or test is modified
   except one **flag-gated** branch in `run_turn`. Everything else is new files.
2. **Schema first, born tenant-safe.** Every new table ships with its RLS policy in the
   **same** migration that creates it (no unprotected window), denormalized `user_id`,
   fail-closed GUC predicate, and a conditional `gummy_app` grant — the Phase 2 pattern.
3. **Flag-gated cutover.** The Orchestrator path is gated by
   `agents_orchestration_enabled` (default **off**) with a guaranteed fallback to the
   Phase 2 `generate_grounded_reply`. Default-on is the *last* milestone, only after
   parity + evals pass.
4. **Reuse, never reimplement.** Memory, retrieval, context assembly, prompt building,
   embeddings, LLM gateway, and the enrichment worker are reused as-is.
5. **Hermetic-first, live-verified.** Default suite is SQLite + fake providers; every new
   table gets a skip-gated live-Postgres RLS isolation test under `gummy_app`.
6. **Green-only execution in Phase 3.** Yellow/Red tools and actions are *modeled and
   gated* but their executors are deferred — no risky action can fire before the approval
   UI exists.

---

## Risk ordering rationale

Milestones are ordered so that **the blast radius grows monotonically**:

- **M1–M3** touch only *new, inert* surface (schema, repos, a trace wrapper). The live
  turn behaves **identically** — these cannot regress the user experience.
- **M4** introduces the Orchestrator but **behind a flag with a hard fallback**; worst
  case is "flag off."
- **M5–M10** add capability incrementally, each flag-gated and reversible by config.
- **M11** is the only behavior-changing flip (default-on) and ships last, gated on parity.

This front-loads the scary, hard-to-reverse work (live-Postgres RLS on 8 tables) while
nothing depends on it, and defers the one irreversible-by-perception change (default
routing) to the very end.

---

## Status board

| Milestone | Scope | Risk | Migrations | Status |
| --- | --- | --- | --- | --- |
| **M1** | Schema & RLS foundation + contract types (inert) | 🟢 Low | 0012–0014 | ⏳ Planned |
| **M2** | Repositories (pure persistence) | 🟢 Low | — | ⏳ Planned |
| **M3** | Agent Registry + Run Recording (behavior identical) | 🟢 Low | — | ⏳ Planned |
| **M4** | Context Builder + Orchestrator (single-agent, flag) | 🟡 Med | — | ⏳ Planned |
| **M5** | Agent Router + 2nd agent (pipeline) | 🟡 Med | — | ⏳ Planned |
| **M6** | Tool Execution Interface + Policy Engine (Green only) | 🟠 Med-High | 0015 | ⏳ Planned |
| **M7** | Shared agent memory writes + provenance | 🟡 Med | 0016 | ⏳ Planned |
| **M8** | Goal & Task Foundation (services + API) | 🟡 Med | 0017 | ⏳ Planned |
| **M9** | Agent-to-agent trace + parallel compose | 🟠 Med-High | — | ⏳ Planned |
| **M10** | Action approvals (pending handles, no executors) | 🟠 High | 0018 | ⏳ Planned |
| **M11** | Seal — orchestration default-on | 🔴 Highest | — | ⏳ Planned |

> **Flags introduced:** `agents_run_recording` (M3), `agents_orchestration_enabled`
> (M4, default-off until M11). Both default off; each milestone is reversible by clearing
> its flag with zero data risk.

---

## M1 — Schema & RLS foundation + contract types 🟢

**Goal:** create the core framework tables (registry + observability trace) and the
typed contract, all **inert** — nothing reads or writes them yet — so the riskiest live
work (RLS on new tables) lands first, verified, while nothing depends on it. Mirrors
Phase 2 M1.

**Files impacted (all new, except additive enum/registration):**
- Models: `app/models/agent.py`, `agent_run.py`, `agent_step.py`, `agent_message.py`.
- Enums (additive to `app/models/enums.py`): `RunStatus`, `StepStatus`,
  `AgentMessageRole`, `PermissionTier` (Green/Yellow/Red), `PlanShape`.
- Contract schemas: `app/schemas/agents.py` — `AgentManifest`, `AgentTask`,
  `AgentResult`, `ContextPack`, `RoutingDecision`, `OrchestrationResult` (pure Pydantic;
  zero runtime wiring).
- `app/models/__init__.py` — additive registration only.
- Migrations: `0012_add_agents`, `0013_add_agent_runs` (`agent_runs` + `agent_steps`),
  `0014_add_agent_messages`.

**Database impact:**
- `agents` — registry catalog: `key`, `display_name`, `mission`, `ceiling`,
  `tool_manifest` (JSONB), `model_tier`, `enabled`, nullable `user_id` (reserved for
  user-defined agents; global rows have `user_id IS NULL`).
- `agent_runs` — `id`, `user_id`, `conversation_id?`, `trigger` (chat|scheduler),
  `route_plan` (JSONB), `status`, `cost_tokens`, `cost_usd`, timestamps.
- `agent_steps` — `id`, `run_id`, `user_id`, `agent_key`, `seq`, `status`, `input`/
  `output` (JSONB), `cost_*`, timestamps; `UNIQUE(run_id, seq)`.
- `agent_messages` — `id`, `run_id`, `user_id`, `from_agent`, `to_agent?`, `role`,
  `payload` (JSONB), `seq`, timestamps; `UNIQUE(run_id, seq)`.
- Every table: RLS enabled in-migration, fail-closed GUC policy
  (`user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid`),
  conditional `gummy_app` grant, string-backed enums + CHECK. `agents` global rows are
  read-only to tenants (policy allows `user_id IS NULL OR user_id = GUC` on read).

**Services:** none (inert milestone).

**APIs:** none.

**Tests:**
- `test_agent_models.py` — table/column/index/constraint/enum registration, FK wiring,
  identifier ≤ 63 chars, JSONB mapping, "Phase 1/2 untouched" sanity check.
- `test_agents_contract.py` — `AgentTask`/`AgentResult` round-trip serialization, schema
  validation, default fields.
- `test_rls_postgres.py` — extend with `test_agent_tables_isolation_under_rls` (gated on
  `RUN_RLS_PG_TESTS` + `RLS_TEST_DSN`): insert a run→step→message chain per tenant,
  assert isolation + fail-closed + WITH-CHECK rejection across the new tables.

**Verification steps:**
- Models import + `Base.metadata.create_all` on SQLite (all tables build).
- `alembic heads` → single head `0014`; `alembic history` linear `0011…0014`.
- `alembic upgrade 0011:head --sql` offline render (DDL: tables, RLS, CHECKs, JSONB,
  grants).
- `ruff` / `mypy` clean.
- `pytest` full suite green (baseline + new model/contract tests).
- **Live gate (Postgres, `gummy_app`):** `upgrade head`, `downgrade 0011 → upgrade head`
  cycle; RLS enabled + 1 policy/table; `gummy_app` CRUD grants present; isolation +
  fail-closed + WITH-CHECK pass; Supabase advisors flag nothing new.

**Rollback strategy:** `alembic downgrade 0011` drops all four tables; revert the
additive enum/model/registration changes. **Zero data risk** — tables are empty and
unreferenced. Schema-only, fully reversible.

---

## M2 — Repositories (pure persistence) 🟢

**Goal:** the data-access layer for the M1 tables — module functions, `build/run`
queries, `flush()` never `commit()`, no business logic. Mirrors Phase 2 M2. Still inert
(no service consumes them yet).

**Files impacted (all new):**
- `app/repositories/agent_repository.py` — `get(key)`, `list_enabled(user_id)`,
  `upsert_catalog(...)` (for seeding).
- `app/repositories/agent_run_repository.py` — `create`, `get`, `list_for_conversation`,
  `set_status`, `add_cost`.
- `app/repositories/agent_step_repository.py` — `append` (assigns `seq`), `list_for_run`.
- `app/repositories/agent_message_repository.py` — `append` (assigns `seq`),
  `list_for_run`.

**Database impact:** none (no migration; reads/writes M1 tables only).

**Services:** none.

**APIs:** none.

**Tests:**
- `test_agent_repository.py` — CRUD, tenant scoping, `seq` assignment + ordering,
  cost accumulation, enabled-filter, global-vs-user agent rows. (SQLite-testable; any
  Postgres-only query ships a pure `build_*_statement` compile test, per the Phase 2
  search-repo pattern.)

**Verification steps:** `ruff`/`mypy` clean; `pytest` full suite green (+repo tests);
`alembic heads` unchanged at `0014`; live RLS gate re-run (no regression, no migration).

**Rollback strategy:** delete the new repository files. No schema, no behavior, no data —
trivially reversible.

---

## M3 — Agent Registry + Run Recording 🟢

**Goal:** stand up the **Registry** (in-code manifests overlaid with the `agents` table)
and a **Run Recorder** so that `run_turn` writes a single-agent "general" run wrapping
**today's `generate_grounded_reply` unchanged**. Behavior is **byte-for-byte identical**;
the turn is now *traced*. Flag-gated by `agents_run_recording`.

**Files impacted:**
- New: `app/services/agents/registry.py` (manifest loader + validation: ceiling ≥ any
  tool tier; tools exist), `app/services/agents/manifests/` (in-code built-in manifests,
  starting with one `general` agent), `app/services/agents/run_recorder.py`.
- Modified (additive, flag-gated): `app/services/conversation/conversation_turn_service.py`
  — when `agents_run_recording` is on, open an `agent_run`, record one `agent_step`
  around the existing reply call, set status/cost; **the reply itself is unchanged**.
- Modified: `app/core/config.py` (+`agents_run_recording`, default false),
  `app/main.py` (registry built + built-ins seeded into `agents` at lifespan, only when
  a DB is configured — mirrors worker startup).

**Database impact:** none (no migration). Seeds catalog rows into `agents` at startup
(idempotent upsert).

**Services:** `registry`, `run_recorder`. Both flush; `run_turn` still owns the single
commit (the run/step rows commit atomically with the messages).

**APIs:** none required. (Optional, deferred: `GET /api/v1/agents` for the UI.)

**Tests:**
- `test_agent_registry.py` — manifest validation (reject ceiling < tool tier, unknown
  tool), lookup, global+user enablement.
- `test_run_recorder.py` — a flag-on turn writes exactly one run + one step with correct
  status/cost; a flag-off turn writes nothing.
- `test_conversation_turn_service.py` (additive cases only) — **parity:** flag-on vs
  flag-off produce an identical reply + identical message persistence.

**Verification steps:** `ruff`/`mypy` clean; full suite green; **parity assertion** (reply
identical with recording on/off); live RLS gate green; head unchanged at `0014`.

**Rollback strategy:** set `agents_run_recording=false` (config toggle) → the turn
reverts to the pure Phase 2 path; trace rows simply stop being written. No migration to
reverse, no data risk.

---

## M4 — Context Builder + Orchestrator (single-agent) 🟡

**Goal:** introduce the **Master Orchestrator** and **Agent Context Builder**. Behind
`agents_orchestration_enabled` (default off), `run_turn` delegates to `orchestrate(...)`
which runs a single general-purpose agent handler and returns a reply-shaped result —
with a **guaranteed fallback** to `generate_grounded_reply` on any orchestrator error.
**Parity with Phase 2 is the gate.**

**Files impacted:**
- New: `app/services/agents/orchestrator_service.py`,
  `app/services/agents/context_builder.py`,
  `app/services/agents/handlers/general_agent.py`.
- Modified (additive, flag-gated): `conversation_turn_service.run_turn` — branch on
  `agents_orchestration_enabled`; fallback wrapper around `orchestrate`.
- Modified: `app/core/config.py` (+`agents_orchestration_enabled`, default false),
  `app/core/constants.py` (per-run step cap, cost cap).

**Database impact:** none (no migration). Writes `agent_runs`/`agent_steps` via M2 repos.

**Services:** `orchestrator_service` (compose, gate-passthrough for now since only Green),
`context_builder` (wraps `memory_retrieval_service` + `context_assembly_service` +
`prompt_builder` + recent-messages/summary repos). The general agent handler is a pure
`AgentTask → AgentResult` function reusing the existing retrieve→assemble→prompt→LLM core.

**APIs:** none (internal to the existing turn endpoint).

**Tests:**
- `test_context_builder.py` — pack contents, token budgeting, dedupe, per-agent scoping.
- `test_orchestrator_service.py` — single-agent orchestration; **fallback** path on
  forced handler error returns a valid reply; step/cost caps enforced.
- `test_conversation_turn_service.py` — **parity (critical):** with
  `agents_orchestration_enabled` on, the single-agent route produces a reply equivalent
  to `generate_grounded_reply` for the same input; foreign-tenant turn still 404s.

**Verification steps:** `ruff`/`mypy` clean; full suite green; **parity suite passes**
(orchestrated == legacy for single-agent); fallback verified (kill the handler → user
still gets a reply); live RLS gate green; head unchanged.

**Rollback strategy:** `agents_orchestration_enabled=false` → `run_turn` uses the Phase 2
path verbatim. Config toggle, no schema, no data risk. The legacy core is never deleted.

---

## M5 — Agent Router + second agent (pipeline) 🟡

**Goal:** add the **Router** (rules-first → LLM-fallback on the cheap tier) and a second
trivial specialist (a read-only "Recall/Research" agent) to exercise routing **and** a
pipeline hand-off. Still Green-only, still flag-gated.

**Files impacted:**
- New: `app/services/agents/router.py`,
  `app/services/agents/handlers/recall_agent.py`, manifest for it.
- Modified: `orchestrator_service` — consume `RoutingDecision` (single | pipeline);
  record `route_plan` on the run. `app/core/config.py` — cheap-tier model id for the
  router fallback (the `claude_model_fast` seam).

**Database impact:** none (no migration; `route_plan` already on `agent_runs` from M1).

**Services:** `router` (layered: `agent_context` hint → keyword/intent rules → LLM
fallback → low-confidence default to `general`). Orchestrator gains pipeline execution
(output of step N → inputs of step N+1).

**APIs:** none.

**Tests:**
- `test_router.py` — deterministic rules path (agent_context + keywords) routes without
  an LLM call; ambiguous → LLM fallback (faked); low-confidence → general default.
- `test_orchestrator_pipeline.py` — two-step pipeline hands off correctly; cost
  accumulates; loop guard halts an injected cycle.
- **Router eval fixture** (`tests/evals/`) — labeled intent→agent set scored for accuracy
  (eval, not a hard CI gate).

**Verification steps:** `ruff`/`mypy` clean; full suite green; router cost/latency budget
asserted on the fallback; pipeline parity (a single-agent intent still routes to
`general` and matches M4); live RLS gate green.

**Rollback strategy:** `agents_orchestration_enabled=false` disables the whole path; or
ship M5 with the router defaulting every intent to `general` (a one-line config) to
neutralize routing while keeping the code. Config-level, no data risk.

---

## M6 — Tool Execution Interface + Policy Engine (Green only) 🟠

**Goal:** the single, typed, **policy-gated** door for tool calls, with the Green/Yellow/
Red **Policy Engine**. Phase 3 implements **Green executors only** (web search, memory
read, document read); Yellow/Red tools are **modeled + gated but executors deferred**
(they return a "pending"/"blocked" decision, never run). This is the first milestone that
enforces a *security* invariant, hence the higher risk.

**Files impacted:**
- New: `app/services/agents/tools/` (`interface.py` `ToolInterface` protocol,
  `catalog.py`, Green adapters: `web_search.py`, `memory_read.py`, `doc_read.py`),
  `app/services/agents/policy_engine.py`.
- New model/migration: `app/models/tool_invocation.py`; `0015_add_tool_invocations`.
- Modified: agent handlers call tools **only** via `ToolInterface`; manifests declare
  their tool keys.

**Database impact:**
- `tool_invocations` — `id`, `user_id`, `run_id`, `agent_key`, `tool_key`, `args` (JSONB),
  `tier`, `decision` (allowed|blocked|pending), `status`, `output_ref?`, `cost_*`,
  timestamps. RLS in-migration, fail-closed, `gummy_app` grant, append-only semantics.

**Services:** `policy_engine` (evaluate tier × user settings × standing allowances →
allow|prompt|block); `ToolInterface.invoke` (manifest check **and** policy gate **and**
untrusted-output handling, then Green-execute or return pending/blocked) + an audit write.

**APIs:** none in this milestone (approval endpoints arrive with M10).

**Tests:**
- `test_policy_engine.py` — full Green/Yellow/Red matrix: manifest check, ceiling
  enforcement, standing allowances, **no always-allow for Red**, and the
  **prompt-injection invariant** (external tool content cannot escalate tier or
  self-approve).
- `test_tool_interface.py` — Green tool runs + audited; tool not in manifest → blocked;
  Yellow/Red → pending handle, **never executed**; cost recorded.
- `test_rls_postgres.py` — `tool_invocations` isolation + fail-closed (gated).

**Verification steps:** `ruff`/`mypy` clean; full suite green; **policy matrix exhaustive
+ green**; injection test proves no escalation; `0015` applied to live Postgres + down/up
cycle; live RLS gate (now incl. `tool_invocations`) green.

**Rollback strategy:** flag-off disables agent tool use entirely; the Green-only scope
means no external side effect ever fired. Schema rollback: `alembic downgrade 0014` drops
`tool_invocations` (empty table). Config + reversible migration.

---

## M7 — Shared agent memory writes + provenance 🟡

**Goal:** let agents **propose** memories that persist through the existing consent gate
and Memory Engine, tagged with `source_kind='agent'` provenance — the "shared provenance
bus" seam. Reuse only; no new memory logic.

**Files impacted:**
- New: `app/services/agents/agent_memory.py` (thin facade: `recall` → existing retrieval;
  `propose` → consent gate → `memory_service.create_memory` +
  `memory_source_repository.link_source`).
- Migration: `0016_widen_source_kind` — extend the `memory_sources.source_kind`
  CHECK/enum to add `agent` (reserve `document`, `activity`). Additive constraint change,
  no data migration.
- Modified: `orchestrator_service` routes `AgentResult.proposed_memories` through the
  facade after composing.

**Database impact:** `memory_sources.source_kind` constraint widened (existing
`conversation` rows untouched). No new table.

**Services:** `agent_memory` (delegates to Phase 1 `memory_service` /
`memory_retrieval_service` and Phase 2 `memory_source_repository`). Consent uses the
existing `ConsentMode` exactly as Phase 2 extraction does; agents never write directly.

**APIs:** none (the Memory Center `/api/v1/memories/*` already surfaces results).

**Tests:**
- `test_agent_memory.py` — `recall` scoping; `propose` under autonomous (writes +
  `source_kind='agent'` provenance) vs assisted/explicit (writes nothing); routed through
  `memory_service` (default scores, embedding enqueue).
- `test_rls_postgres.py` — provenance isolation re-verified with the widened enum (gated).
- Migration test — `0016` up/down preserves existing `conversation` rows; constraint
  accepts `agent`, rejects unknown kinds.

**Verification steps:** `ruff`/`mypy` clean; full suite green; consent gate honored;
provenance verified; `0016` live up/down cycle; live RLS gate green.

**Rollback strategy:** flag-off stops agent writes (no agent-sourced memories created).
Schema: `downgrade 0016` restores the prior CHECK — safe because no `agent`-kind rows
exist while the flag is off. Reversible.

---

## M8 — Goal & Task Foundation 🟡

**Goal:** the durable work backbone — `goals` decomposed into `tasks` with status — that
GSD and the Multi-Agent Workforce build on. The Orchestrator can create/advance tasks;
the Context Builder surfaces active items into packs.

**Files impacted:**
- New models: `app/models/goal.py`, `app/models/task.py`; enums `GoalStatus`,
  `TaskStatus`; migration `0017_add_goals_tasks`.
- New repos: `app/repositories/goal_repository.py`, `task_repository.py` (flush-only).
- New services: `app/services/agents/goal_service.py`, `task_service.py`.
- New API: `app/api/v1/goals.py` (+ tasks); registered in `router.py`. Schemas:
  `app/schemas/goal.py`, `task.py`.
- Modified: `context_builder` reads active goals/tasks into the pack; `orchestrator_service`
  can create/advance tasks within the turn's unit of work.

**Database impact:**
- `goals` — `id`, `user_id`, `title`, `description?`, `status{active,paused,done,
  abandoned}`, `agent_context`, `priority?`, `target_date?`, timestamps.
- `tasks` — `id`, `user_id`, `goal_id?`, `agent_key?`, `agent_run_id?` (FK→`agent_runs`,
  `ON DELETE SET NULL`), `title`, `status{pending,in_progress,blocked,done,cancelled}`,
  `seq`/ordering, `result_ref?`, timestamps.
- Both: RLS in-migration, fail-closed, `gummy_app` grant, string enums + CHECK.

**Services:** `goal_service` (create/list/update/complete), `task_service` (create/
advance/block/complete). Services own the commit; repos flush.

**APIs:** `GET/POST/PATCH /api/v1/goals`, `GET/POST/PATCH /api/v1/tasks` (tenant-scoped,
standard `{error}` envelope, pagination). Thin HTTP → service delegation.

**Tests:**
- `test_goal_task_repository.py` / `_service.py` — CRUD, status transitions, ordering,
  goal→task linkage, run provenance, tenant scoping.
- `test_goal_task_api.py` — endpoints, validation (empty update → 400), foreign-tenant →
  404/empty.
- `test_rls_postgres.py` — `goals`/`tasks` isolation + fail-closed (gated).

**Verification steps:** `ruff`/`mypy` clean; full suite green; app-level tenant isolation
(foreign tenant sees nothing); `0017` live up/down cycle; live RLS gate green.

**Rollback strategy:** the goals/tasks API and services are additive — unregister the
router and `downgrade 0017` (tables empty unless agents created tasks; if so, export
first). Reversible; the only milestone adding user-visible read/write endpoints, so treat
its rollback as "remove endpoints + drop tables" in a maintenance window.

---

## M9 — Agent-to-agent trace + parallel compose 🟠

**Goal:** persist inter-agent hand-offs as `agent_messages` (the audit trail) and add
**parallel fan-out / gather** with a Personality-shaped compose step. No new schema
(`agent_messages` exists from M1).

**Files impacted:**
- New: `app/services/agents/compose.py` (merge parallel outputs; Personality voice hook).
- Modified: `orchestrator_service` — write an `agent_messages` row per hop; add the
  parallel pattern (fan-out then gather) alongside single/pipeline.

**Database impact:** none (writes M1's `agent_messages`).

**Services:** orchestrator parallel execution + `compose`. Loop/cost guards extended to
the fan-out case.

**APIs:** none (a future Activity-Feed read endpoint may surface the trace).

**Tests:**
- `test_orchestrator_parallel.py` — fan-out runs concurrently, gather merges,
  `agent_messages` records every hop in order; one failing branch is isolated and the run
  still composes a reply.
- `test_compose.py` — deterministic merge; Personality hook applied last.
- `test_rls_postgres.py` — `agent_messages` isolation re-verified under multi-agent runs.

**Verification steps:** `ruff`/`mypy` clean; full suite green; concurrency correctness
(no cross-tenant bleed under parallel sessions); loop/cost guard halts a forced cascade;
live RLS gate green.

**Rollback strategy:** flag-off disables orchestration; or restrict the Router to
single/pipeline shapes (config) to neutralize parallelism while keeping the code. No
schema change to reverse. Config-level, no data risk.

---

## M10 — Action approvals (pending handles, no executors) 🟠

**Goal:** wire the **human-in-the-loop seam** — the Policy gate's "prompt" path creates a
previewed `action_approvals` row and returns a pending handle; an approve/reject endpoint
records the decision. **No Yellow/Red executor is wired** — approving does not yet fire an
external action (that's Phase 4). This de-risks the seam without enabling any irreversible
action.

**Files impacted:**
- New model/migration: `app/models/action_approval.py`; `0018_add_action_approvals`.
- New repo/service: `app/repositories/action_approval_repository.py`,
  `app/services/agents/approval_service.py`.
- New API: `app/api/v1/actions.py` — `GET /api/v1/actions`,
  `POST /api/v1/actions/{id}/approve|reject`. Schemas in `app/schemas/action.py`.
- Modified: `policy_engine`/`ToolInterface` — the "prompt" decision creates a pending
  approval instead of returning a bare pending flag.

**Database impact:**
- `action_approvals` — `id`, `user_id`, `run_id?`, `agent_key`, `action_kind`, `tier`,
  `preview` (JSONB), `status{pending,approved,rejected,expired}`, `decided_at?`,
  `expires_at`, timestamps. RLS in-migration, fail-closed, `gummy_app` grant, append-only
  decision trail (security-system §7).

**Services:** `approval_service` (list pending, approve/reject with expiry + audit). The
**executor remains stubbed** — approval flips status and records the decision; it does not
perform the side effect.

**APIs:** the approval endpoints above (tenant-scoped, step-up-auth seam reserved for Red;
standard envelope).

**Tests:**
- `test_approval_service.py` — pending creation from a Yellow/Red gate decision;
  approve/reject transitions; expiry; **no executor fires on approve** (asserted).
- `test_actions_api.py` — list/approve/reject, foreign-tenant → 404, auth required, Red
  has no always-allow.
- `test_rls_postgres.py` — `action_approvals` isolation + fail-closed (gated).

**Verification steps:** `ruff`/`mypy` clean; full suite green; **invariant: approving a
Red action performs no external side effect** (executor deferred); `0018` live up/down
cycle; live RLS gate green.

**Rollback strategy:** flag-off disables agent actions; endpoints are additive (unregister
+ `downgrade 0018`, table empty of real side effects since no executor exists). Because no
external action ever fired, rollback carries no outside-world consequences.

---

## M11 — Seal — orchestration default-on 🔴

**Goal:** after the full parity suite and router/eval gates pass, flip
`agents_orchestration_enabled` **on by default**, keeping `generate_grounded_reply` as the
permanent single-agent fallback. Produce the as-implemented `PHASE3_ARCHITECTURE.md` and
tag `phase3-complete`. This is the only milestone that changes default behavior.

**Files impacted:**
- Modified: `app/core/config.py` — default `agents_orchestration_enabled=true`.
- New doc: `docs/PHASE3_ARCHITECTURE.md` (as-built, mirroring PHASE2_ARCHITECTURE.md).
- No code paths removed — the Phase 2 reply core stays as the fallback (mirrors Phase 2
  M8 keeping `generate_grounded_reply` after retiring `/chat`).

**Database impact:** none.

**Services:** none new — only the default flag value changes.

**APIs:** none new.

**Tests:** full M1–M10 regression with the flag **on by default**; parity suite green;
router eval above threshold; fallback still triggers on injected orchestrator failure.

**Verification steps:** full suite green with default-on; live RLS + isolation gate (all
new tables) green; migration head (local == live) at `0018`; Supabase advisors clean;
manual smoke of a Career-style and a recall-style turn end-to-end.

**Rollback strategy:** **single config toggle** — set `agents_orchestration_enabled=false`
to instantly revert every turn to the verified Phase 2 path. No schema or data change.
This is why the legacy core is never deleted: default-on is reversible in one env var.

---

## Cross-cutting

**Frozen seams reused unchanged:** JWT auth, tenant GUC, the RLS pattern, the Memory
Engine (`memory_service`), hybrid retrieval, context assembly, prompt builder, embeddings,
the LLM gateway, and the enrichment worker. Phase 3 composes these; it modifies none.

**Migration ledger:** `0012` agents · `0013` agent_runs+steps · `0014` agent_messages ·
`0015` tool_invocations · `0016` widen source_kind · `0017` goals+tasks · `0018`
action_approvals. All additive, all RLS fail-closed under `gummy_app`, all with down
paths. Short Alembic revision ids (≤ VARCHAR(32) — the Phase 2 lesson).

**Quality gate (every milestone):** `ruff` + `mypy` + `pytest` stay green; the fast suite
stays hermetic/offline; each new table adds a skip-gated live-Postgres isolation test;
no Phase 1/1.5/2 file is modified except the one flag-gated `run_turn` branch.

**Deferred to Phase 4+ (explicitly NOT Phase 3):** rich domain agents (Career, Learning,
Fitness, Marketing, Research, Business), Yellow/Red tool **executors**, the approval UI,
LangGraph supervisor sub-graphs, the GSD scheduler worker, and the Workflow-Learning
miner. Phase 3 ships the **framework + trace tables + Green path + goals/tasks**, proven
by trivial agents — so Phase 4 is pure addition.

**Checkpoints:** tag each milestone (`phase3-m1` … `phase3-m10`) and `phase3-complete`,
matching the Phase 2 checkpoint discipline.

---

_Related: [PHASE3_PLAN.md](PHASE3_PLAN.md) (design of record) ·
[PHASE2_PROGRESS.md](PHASE2_PROGRESS.md) (the milestone discipline this follows) ·
[PHASE1_5_PLAN.md](PHASE1_5_PLAN.md) (flag-gated, reversible rollout precedent) ·
[../architecture/agent-framework.md](../architecture/agent-framework.md) ·
[../architecture/security-system.md](../architecture/security-system.md)._
