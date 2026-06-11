# GUMMY OS — Phase 3 Progress

Living log of Phase 3 (Agent Framework / Master Orchestrator) implementation.
Design of record: [PHASE3_PLAN.md](PHASE3_PLAN.md). Implementation roadmap:
[PHASE3_PROGRESS_PLAN.md](PHASE3_PROGRESS_PLAN.md). Updated continuously,
milestone by milestone.

Baseline at start: tag `phase2-complete`, migration head
`0011_extraction_watermark`, test suite `203 passed, 3 skipped`.

---

## Status board

| Milestone | Scope | Status |
| --- | --- | --- |
| **M1** | Schema & RLS foundation + contract types (migrations 0012–0014) | ✅ **Complete & gate-verified on live Postgres** |
| **M2** | Repositories (pure persistence) | ✅ **Complete** |
| **M3** | Agent Registry + Run Recording | ✅ **Complete** (flag `agents_run_recording`, default off) |
| **M4** | Context Builder + Orchestrator (single-agent, flag) | ✅ **Complete** (flag `agents_orchestration_enabled`, default off) |
| **M5** | Agent Router + 2nd agent (pipeline) | ✅ **Complete** (LLM fallback opt-in via `agents_router_llm_fallback`) |
| **M6** | Tool Execution Interface + Policy Engine (Green only) | ⏳ Planned |
| **M7** | Shared agent memory writes + provenance | ⏳ Planned |
| **M8** | Goal & Task Foundation | ⏳ Planned |
| **M9** | Agent-to-agent trace + parallel compose | ⏳ Planned |
| **M10** | Action approvals (pending handles, no executors) | ⏳ Planned |
| **M11** | Seal — orchestration default-on | ⏳ Planned |

---

## M1 — Schema & RLS foundation + contract types ✅

**Goal:** the core framework tables (registry + observability trace) and the
typed contract, all **inert** — nothing reads or writes them yet — so the
riskiest live work (RLS on new tables) lands first while nothing depends on it.

### Delivered

**Enums** ([app/models/enums.py](../backend/app/models/enums.py), additive only):
`PermissionTier` (green/yellow/red), `RunTrigger` (chat/scheduler), `RunStatus`,
`StepStatus`, `AgentMessageRole` (task/result/error), `PlanShape`
(single/pipeline/parallel).

**Models** (new files):
- [agent.py](../backend/app/models/agent.py) — `agents` registry catalog
  (nullable `user_id`: NULL = built-in global row; `tool_manifest` JSONB;
  `ceiling` permission tier; `uq_agents_key`).
- [agent_run.py](../backend/app/models/agent_run.py) — `agent_runs`
  (one per orchestration; `route_plan` JSONB; cost columns;
  `conversation_id` FK `SET NULL` so the audit trail survives thread deletion).
- [agent_step.py](../backend/app/models/agent_step.py) — `agent_steps`
  (one per agent invocation; `input`/`output` JSONB; `UNIQUE(run_id, seq)`).
- [agent_message.py](../backend/app/models/agent_message.py) — `agent_messages`
  (append-only inter-agent audit trail; `UNIQUE(run_id, seq)`).
- [models/__init__.py](../backend/app/models/__init__.py) — registration
  (additive only). Every table carries a denormalized `user_id`.

**Contract schemas** ([app/schemas/agents.py](../backend/app/schemas/agents.py),
pure Pydantic, zero runtime wiring): `AgentManifest` (frozen), `AgentTask`,
`AgentResult`, `ContextPack`, `CostInfo`, `RouteStep`, `RoutingDecision`,
`OrchestrationResult`.

**Migrations** (linear `0011 → 0014`):
- `0012_add_agents` — registry table + **three policies**: `agents_global_read`
  (tenants read global rows), `agents_tenant_isolation` (standard fail-closed),
  `agents_global_seed` (global rows writable **only when no tenant GUC is
  set** — the M3 startup-seed path; global rows are read-only inside any
  tenant transaction).
- `0013_add_agent_runs` — `agent_runs` + `agent_steps`, standard fail-closed
  policy each.
- `0014_add_agent_messages` — `agent_messages`, standard fail-closed policy.

Every table: RLS enabled in the same migration that creates it, the identical
GUC predicate (`user_id = NULLIF(current_setting('app.current_user_id', true),
'')::uuid`), conditional `gummy_app` grant, string enums + named CHECKs.

**Tests**:
- [test_agent_models.py](../backend/tests/test_agent_models.py) — 18 tests:
  table/column/index/constraint/FK registration, `SET NULL` audit-survival FK,
  denormalized `user_id` everywhere, enum values, 63-char identifier guard,
  Phase 1/2-untouched sanity, and a full ORM chain round-trip on SQLite.
- [test_agents_contract.py](../backend/tests/test_agents_contract.py) — 8 tests:
  defaults, validation bounds, frozen manifests, JSON round-trips.
- [test_rls_postgres.py](../backend/tests/test_rls_postgres.py) — extended with
  `test_agent_tables_isolation_under_rls` (skip-gated): run→step→message chain
  isolation, fail-closed, WITH-CHECK rejection, **and** the `agents` catalog
  semantics (tenant reads global rows; tenant cannot INSERT or UPDATE them;
  no-GUC seed path can).

### Verification performed

| Check | Result |
| --- | --- |
| Models import + `Base.metadata.create_all` on SQLite | ✅ all 4 new tables build; ORM chain round-trips |
| `alembic heads` | ✅ single head `0014_add_agent_messages` |
| `alembic history` | ✅ linear `0011 → 0014`, no branches |
| `alembic upgrade 0011:0014 --sql` (offline render) | ✅ tables, 6 policies, CHECKs, JSONB, conditional grants |
| `ruff check .` | ✅ all checks passed |
| `mypy app` | ✅ no issues in 98 files |
| `pytest` (full suite) | ✅ **228 passed, 4 skipped** (was 203/3; +26 tests, +1 skip-gated RLS test) |

### M1 gate — CLOSED ✅ (live Postgres, `gummy_app` non-bypass role)

| Gate check | Result |
| --- | --- |
| `alembic upgrade head` on live Postgres | ✅ 0012–0014 applied (head was 0011) |
| `alembic downgrade 0011` → `upgrade head` cycle | ✅ clean both ways |
| Run/step/message isolation | ✅ Bob sees 0 of Alice's |
| Fail-closed (unset GUC) on all tenant tables | ✅ zero rows |
| WITH CHECK rejection (forged `user_id`) | ✅ rejected on `agent_runs` |
| `agents` global rows readable by tenants | ✅ |
| `agents` global rows **not writable** by tenants | ✅ INSERT rejected, UPDATE affects 0 rows |
| `agents` global rows writable on no-GUC seed path | ✅ (how M3 seeding works) |
| All 4 gated RLS tests (`pytest tests/test_rls_postgres.py`) | ✅ 4 passed |
| Supabase security advisors | ✅ nothing new (4 pre-existing findings only) |

### Issues found & resolved during M1

1. **`agents` needed a three-policy design, not the standard single policy.**
   Global catalog rows (`user_id IS NULL`) must be readable by every tenant but
   seeded/updated by the app at startup — and the startup path runs with no
   tenant GUC. A single fail-closed policy would block both. Solved with
   `agents_global_read` (SELECT only) + `agents_tenant_isolation` (standard) +
   `agents_global_seed` (writes allowed only when `user_id IS NULL` **and** the
   GUC is unset), keeping global rows read-only inside tenant transactions.
   Proven live by the new RLS test.

### Rollback

`alembic downgrade 0011_extraction_watermark` drops all four tables (verified
live); revert the additive enum/model/schema/test changes. Zero data risk —
nothing reads or writes these tables yet.

---

## M2 — Repositories (pure persistence) ✅

**Goal:** the data-access layer for the M1 tables — module functions,
`flush()` never `commit()`, no business logic, every query tenant-scoped on
the denormalized `user_id`. Still inert: no service consumes them yet.

### Delivered

**Repositories** (new files, all flush-only):
- [agent_repository.py](../backend/app/repositories/agent_repository.py) —
  `get_by_key`, `list_enabled` (global + own rows, enabled filter),
  `upsert_catalog` (idempotent global-row seed; refreshes manifest fields but
  **preserves `enabled`** so a manual disable survives redeploys).
- [agent_run_repository.py](../backend/app/repositories/agent_run_repository.py)
  — `create_run`, `get_run`, `list_for_conversation` (newest first),
  `set_status` (stamps `finished_at` on terminal states), `add_cost`
  (Decimal-safe accumulation).
- [agent_step_repository.py](../backend/app/repositories/agent_step_repository.py)
  — `next_seq`, `append_step` (assigns monotonic per-run seq), `list_for_run`.
- [agent_message_repository.py](../backend/app/repositories/agent_message_repository.py)
  — `next_seq`, `append_message`, `list_for_run`.

**Tests**:
- [test_agent_repository.py](../backend/tests/test_agent_repository.py) —
  11 tests: catalog upsert insert/refresh (+`enabled` preservation),
  global-vs-user visibility, run defaults, tenant scoping (foreign tenant
  sees nothing), status + `finished_at`, cost accumulation, newest-first
  listing, per-run seq monotonicity (independent across runs), ordered +
  scoped step/message listing.

### Verification performed

| Check | Result |
| --- | --- |
| `ruff check .` | ✅ all checks passed |
| `mypy app` | ✅ no issues in 102 files |
| `pytest` (full suite) | ✅ **239 passed, 4 skipped** (was 228/4; +11 repo tests) |
| `alembic heads` | ✅ unchanged at `0014_add_agent_messages` (no migration) |
| Live RLS gate re-run (4 gated tests under `gummy_app`) | ✅ 4 passed, no regression |

### Rollback

Delete the four repository files + test file. No schema, no behavior, no data
— trivially reversible.

---

## M3 — Agent Registry + Run Recording ✅

**Goal:** stand up the Registry (in-code manifests + the `agents` DB overlay)
and a Run Recorder so a flag-on turn is traced as a single-agent "general"
run wrapping **today's `generate_grounded_reply` unchanged**. Behavior
identical; flag `agents_run_recording` (default **off**).

### Delivered

**New services** (`app/services/agents/`):
- [manifests.py](../backend/app/services/agents/manifests.py) — in-code
  built-ins; one `general` agent (Green, no tools).
- [registry.py](../backend/app/services/agents/registry.py) — `AgentRegistry`:
  validates at construction (duplicate key / unknown tool / ceiling below a
  tool's tier → `ManifestValidationError`), `get`/`keys`/`list_enabled`
  (DB-overlay enablement), `seed_catalog` (idempotent global-row upsert),
  `get_registry()` singleton. `KNOWN_TOOL_TIERS` is empty until M6's catalog
  replaces it — any tool declaration is rejected today.
- [run_recorder.py](../backend/app/services/agents/run_recorder.py) —
  `start_run` (run + first step, flush-only), `finish_success` (status, output,
  cost accumulation), `finish_failure` (error trail). Flush-only: the trace
  commits atomically with the turn's messages.

**Modified (additive, flag-gated):**
- [conversation_turn_service.py](../backend/app/services/conversation/conversation_turn_service.py)
  — flag-gated recording branch around the unchanged reply call; **lazy
  imports** keep the conversation domain free of a module-level agents
  dependency. On reply failure the failure trace is flushed but the exception
  propagates uncommitted — byte-identical to the unrecorded path.
- [config.py](../backend/app/core/config.py) — `agents_run_recording: bool = False`.
- [main.py](../backend/app/main.py) — lifespan seeds the catalog (idempotent,
  best-effort, only when a DB is configured; runs with no tenant GUC — the
  `agents_global_seed` policy path).
- [agent_step_repository.py](../backend/app/repositories/agent_step_repository.py)
  — added `finish_step` (flush-only finalizer the recorder needs).

**Tests** (+13):
- [test_agent_registry.py](../backend/tests/test_agent_registry.py) — builtin
  validation, unknown key, duplicate key, unknown tool, ceiling-below-tier
  rejection / at-tier acceptance, idempotent seeding, DB-overlay enablement.
- [test_run_recorder.py](../backend/tests/test_run_recorder.py) — recorder
  success/failure lifecycle; flag-off turn writes **zero** trace rows; flag-on
  turn writes exactly one run + one step (status, cost, conversation link,
  previews) with messages persisted unchanged; **parity test**: reply +
  accounting identical flag-on vs flag-off (the M3 gate).

### Verification performed

| Check | Result |
| --- | --- |
| `ruff check .` | ✅ all checks passed |
| `mypy app` | ✅ no issues in 106 files |
| `pytest` (full suite) | ✅ **252 passed, 4 skipped** (was 239/4; +13) |
| **Parity assertion** (reply identical on/off) | ✅ |
| `alembic heads` | ✅ unchanged at `0014_add_agent_messages` (no migration) |
| Live RLS gate re-run (4 gated tests under `gummy_app`) | ✅ 4 passed |
| **Live seed path** (`gummy_app`, no GUC, real Supabase) | ✅ `seeded=1`, global row `('general', enabled, user_id IS NULL)`, re-seed idempotent (total stays 1) |

### Rollback

Set `agents_run_recording=false` (already the default) — the turn reverts to
the pure Phase 2 path; trace rows simply stop being written. No migration to
reverse, no data risk.

---

## M4 — Context Builder + Orchestrator (single-agent) ✅

**Goal:** the Master Orchestrator behind `agents_orchestration_enabled`
(default **off**): `run_turn` delegates to `orchestrate(...)`, which runs the
one `general` agent and returns a reply-shaped result — with a **guaranteed
fallback** to `generate_grounded_reply` on any orchestrator error. Parity
with Phase 2 is the gate.

### Delivered

**New services:**
- [context_builder.py](../backend/app/services/agents/context_builder.py) —
  builds a `ContextPack` per dispatch: ranked memory candidates via the
  unchanged hybrid retrieval, with history/summary supplied by `run_turn`
  (loaded *before* the user message is appended — Phase 2 ordering exactly).
  Goals/tasks stay empty until M8.
- [handlers/general_agent.py](../backend/app/services/agents/handlers/general_agent.py)
  — pure `AgentTask → AgentResult`; reuses `context_assembly_service` +
  `prompt_builder` + the LLM gateway verbatim, so the prompt is identical to
  the legacy core's (the parity mechanism).
- [orchestrator_service.py](../backend/app/services/agents/orchestrator_service.py)
  — `orchestrate(...)`: trace run open → context pack → dispatch →
  finish/cost; `_RunGuard` enforces the per-run step cap and token-cost cap
  (`AGENT_MAX_RUN_STEPS`/`AGENT_MAX_RUN_COST_TOKENS` in constants); failures
  are recorded on the run and re-raised for the caller's fallback.

**Modified:**
- [conversation_turn_service.py](../backend/app/services/conversation/conversation_turn_service.py)
  — three-way flag branch: orchestrated (with try/except fallback to the
  legacy core) → run-recording (M3) → pure legacy. Lazy imports preserved.
- [config.py](../backend/app/core/config.py) — `agents_orchestration_enabled:
  bool = False`.
- [constants.py](../backend/app/core/constants.py) — agent run caps + trace
  preview length.
- [schemas/agents.py](../backend/app/schemas/agents.py) — additive:
  `OrchestrationResult` gains the reply-accounting fields `run_turn` persists
  (`model`, `memories_used`, `input_tokens`, `output_tokens`).

**Tests** (+11):
- [test_context_builder.py](../backend/tests/test_context_builder.py) — pack
  contents/shape, defaults, `max_memories` cap.
- [test_orchestrator_service.py](../backend/tests/test_orchestrator_service.py)
  — guard caps; traced single-agent run (route_plan, status, cost); failure
  recorded + raised; **fallback** (killed handler → user still gets the
  legacy reply, failed run trace committed); **parity (the M4 gate)**:
  orchestrated turn == legacy turn on reply/model/memories/tokens/count;
  foreign-tenant turn still 404s with the flag on.

### Verification performed

| Check | Result |
| --- | --- |
| `ruff check .` | ✅ all checks passed |
| `mypy app` | ✅ no issues in 110 files |
| `pytest` (full suite) | ✅ **263 passed, 4 skipped** (was 252/4; +11) |
| **Parity suite** (orchestrated == legacy, single-agent) | ✅ |
| **Fallback** (handler killed → valid reply) | ✅ |
| `alembic heads` | ✅ unchanged at `0014_add_agent_messages` (no migration) |
| Live RLS gate re-run (4 gated tests under `gummy_app`) | ✅ 4 passed |

### Rollback

`agents_orchestration_enabled=false` (already the default) → `run_turn` uses
the Phase 2 path verbatim. Config toggle, no schema, no data risk. The legacy
core is never deleted.

---

## M5 — Agent Router + second agent (pipeline) ✅

**Goal:** the layered Router (rules-first → LLM-fallback on the cheap tier)
plus a second trivial specialist (the read-only `recall` agent) proving
routing **and** a pipeline hand-off. Still Green-only, still flag-gated.

### Delivered

**New:**
- [router.py](../backend/app/services/agents/router.py) — layered strategy:
  (a) `agent_context` hint (research thread → recall pipeline), (b) keyword
  rules from manifests (deterministic, free), (c) LLM classifier fallback on
  `claude_model_fast` (budget-capped at 8 output tokens, parse-safe, failure
  → default), (d) low-confidence default to single `general`.
- [handlers/recall_agent.py](../backend/app/services/agents/handlers/recall_agent.py)
  — deterministic, LLM-free digest of the pack's ranked memories (zero token
  cost; Green; no side effects). `RECALL_AGENT` manifest with routing
  keywords added to [manifests.py](../backend/app/services/agents/manifests.py).
- [handlers/__init__.py](../backend/app/services/agents/handlers/__init__.py)
  — `dispatch(task, llm)`: the orchestrator's single door to a handler.
- Router eval fixture
  [tests/evals/test_router_eval.py](../backend/tests/evals/test_router_eval.py)
  — 12 labeled intents, accuracy floor 0.8 (deterministic rules score 12/12).

**Modified:**
- [orchestrator_service.py](../backend/app/services/agents/orchestrator_service.py)
  — consumes `RoutingDecision` (single | pipeline); executes steps in order,
  handing prior outputs to the next step via the pack's `scratch`; records
  `route_plan` (+rationale +confidence) on the run; per-step trace via the new
  recorder primitives; loop guard enforced before every dispatch.
- [run_recorder.py](../backend/app/services/agents/run_recorder.py) — additive
  multi-step primitives (`open_run`/`open_step`/`close_step_*`/`close_run_*`);
  the M3 single-step wrappers are unchanged.
- [general_agent.py](../backend/app/services/agents/handlers/general_agent.py)
  — folds pipeline `scratch` digests into the summary block; **empty scratch
  (the single-agent route) leaves the prompt byte-identical** (parity
  invariant).
- [conversation_turn_service.py](../backend/app/services/conversation/conversation_turn_service.py)
  — passes the conversation's `agent_context` into `orchestrate`.
- [config.py](../backend/app/core/config.py) — `agents_router_llm_fallback:
  bool = False`. **Design note:** the roadmap's LLM fallback is implemented
  but opt-in — with only two agents and `general` as a safe catch-all, an LLM
  call on every non-keyword turn would violate the plan's own cost rationale
  (§6.9). The rules path is deterministic and free; the flag turns the
  classifier on when specialist density justifies it.

**Tests** (+13):
- [test_router.py](../backend/tests/test_router.py) — hint/keyword paths route
  with **zero** LLM calls (spy-asserted); ambiguous → LLM fallback on the
  cheap tier (`model` + `max_tokens ≤ 16` asserted — the cost/latency budget);
  unparseable verdict and LLM failure both default to `general`; keyword
  parametrization.
- [test_orchestrator_pipeline.py](../backend/tests/test_orchestrator_pipeline.py)
  — two-step pipeline hands off (recall digest provably reaches the general
  agent's prompt); run cost accumulates; **loop guard halts an injected
  50-step cycle** (run marked failed with the cap error); a single-agent
  intent still routes to `general` and matches the legacy reply exactly.
- Updated (additive evolution): orchestrator metadata assertion gains
  `route_shape`; handler-kill patch target moved to `handlers.general_agent`;
  registry enablement test now set-based over `BUILTIN_MANIFESTS`.

### Verification performed

| Check | Result |
| --- | --- |
| `ruff check .` | ✅ all checks passed |
| `mypy app` | ✅ no issues in 112 files |
| `pytest` (full suite incl. evals) | ✅ **276 passed, 4 skipped** (was 263/4; +13) |
| Router eval accuracy | ✅ 12/12 (floor 0.8) |
| Router fallback budget (cheap model + ≤16 tokens) | ✅ asserted |
| Pipeline parity (non-recall intent == legacy) | ✅ |
| Loop guard (injected cycle halted at cap) | ✅ |
| `alembic heads` | ✅ unchanged at `0014_add_agent_messages` |
| Live RLS gate re-run (4 gated tests under `gummy_app`) | ✅ 4 passed |

### Rollback

`agents_orchestration_enabled=false` disables the whole path;
`agents_router_llm_fallback=false` (default) already neutralizes the LLM
classifier. Config-level, no schema, no data risk.
