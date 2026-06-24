# GUMMY OS — Project Audit

> **Status:** Development-freeze audit, captured 2026-06-24.
> **Scope:** A factual, code-verified snapshot of what exists in the repository at
> the freeze point (end of M8.5). This is the source-of-truth inventory the other
> freeze documents reference. Nothing here is aspirational — every claim was
> checked against the tree, the migrations, the route handlers, and the test run.

---

## 1. Freeze point

| Item | Value |
| --- | --- |
| Freeze milestone | **M8.5 — Search Layer** (seam only; Brave/Tavily not wired) |
| Last commits | `eedcedf` / `eff56e3` — *feat(agents): M8 polish + M8.5 search layer* |
| Phases complete | Phase 0, 1, 1.5, 2, 3 (fully); Phase 4 (partially — M7, M8, M8.5) |
| Remaining in Phase 4 | M9 Workflow Learning, M10 Automation Engine, M11 Multi-Agent Collaboration |
| Backend tests | **598 passed, 4 skipped** (Postgres-gated RLS), 0 failed |
| Migrations | **21** Alembic revisions (`0001` → `0021`) |
| API surface | **~55 endpoints** across 10 routers under `/api/v1` |
| Built-in agents | **7** manifests (General, Recall, + 5 specialists) |

---

## 2. Repository layout (verified)

```
GUMMY-OS/
├── README.md, CONVENTIONS.md, .env.example
├── architecture/            # Design specs + ADRs (Phase 0 → present)
│   ├── system-design.md, database-design.md, tech-stack.md, …
│   └── adrs/ (ADR-001 … ADR-004)
├── docs/                    # Product + phase docs, release notes, this freeze set
├── backend/                 # FastAPI app, agent runtime, services, tests
│   └── app/
│       ├── api/v1/          # 10 route modules
│       ├── core/            # config, security, tenant_context, logging, observability
│       ├── database/        # base, session, 21 migrations
│       ├── models/          # 25 SQLAlchemy models
│       ├── repositories/    # 21 persistence modules (flush-only)
│       ├── schemas/         # Pydantic v2 request/response + internal DTOs
│       ├── services/        # business logic, domain-split (see §4)
│       └── workers/         # embedding_worker, enrichment_worker (async, in-process)
└── frontend/                # Next.js 16 / React 19 web client
    └── src/{app,components,lib,config}
```

---

## 3. Backend module inventory

### 3.1 API routers (`app/api/v1/`)

| Router | Endpoints | Purpose |
| --- | --- | --- |
| `memories.py` | 11 | CRUD, archive/restore, category filter, semantic + keyword search |
| `conversations.py` | 10 | threads, messages, turn, streaming turn, summaries, search, pin/archive |
| `goals.py` | 11 | goal CRUD, status, progress, extraction confirmation |
| `milestones.py` | 2 | goal milestone create/list |
| `tasks.py` | 4 | task CRUD under goals |
| `actions.py` | 4 | action approval queue (Green/Yellow/Red choke point) |
| `files.py` | 6 | upload, list, stats, get, chunks, delete |
| `knowledge.py` | 1 | unified retrieval diagnostics endpoint |
| `agents.py` | 2 | list selectable agents, routing diagnostics |
| `health.py` | 4 | liveness, readiness, LLM probe (+ root) |

All tenant routes are `user_id`-scoped; foreign tenants receive `404`, never `403`.

### 3.2 Models (`app/models/`, 25)

`user`, `memory`, `memory_version`, `memory_embedding`, `memory_source`,
`conversation`, `message`, `conversation_summary`, `conversation_summary_embedding`,
`agent`, `agent_run`, `agent_step`, `agent_message`, `tool_invocation`,
`goal`, `goal_milestone`, `task`, `action_approval`, `file`, `file_chunk`, `enums`.

### 3.3 Repositories (`app/repositories/`, 21)

Pure persistence layer — build/run queries, `flush`, **never commit**. One per
aggregate plus search-specific repos (`conversation_search_repository`,
`search_repository`, `memory_embedding_repository`,
`conversation_summary_embedding_repository`).

### 3.4 Migrations (`app/database/migrations/versions/`, 21)

```
0001 initial memory schema        0012 add agents
0002 memory soft delete           0013 add agent runs
0003 memory embeddings            0014 add agent messages
0004 memory recall tracking       0015 add tool invocations
0005 enable RLS                   0016 widen source kind
0006 add conversations            0017 add goals + tasks
0007 add messages                 0018 add action approvals
0008 conversation summaries       0019 goals M5 fields
0009 memory sources               0020 add goal milestones
0010 add message seq              0021 add files
0011 extraction watermark
```

---

## 4. Services inventory (`app/services/`)

| Domain | Key modules | Phase / Milestone |
| --- | --- | --- |
| `memory/` | memory_service, memory_retrieval_service, context_assembly_service, prompt_builder | Phase 1 |
| `conversation/` | conversation_service, conversation_turn_service, summary_service, memory_extraction_service, conversation_search_service, conversation_continuity_service, enrichment, message_service | Phase 2 |
| `embeddings/` | embedding_service + factory + providers (openai, huggingface, fake) | Phase 1 |
| `llm/` | claude_gateway, openai_gateway, ollama_gateway, factory, fake_provider (behind `LLMProvider` protocol) | Phase 1+ |
| `goals/` | goal_service, goal_extraction_service, milestone_service | M5 / M5.5 |
| `files/` | file_service, extraction_service, chunking_service, file_retrieval_service, file_context_service, storage/* | M6 / M6.5 |
| `knowledge/` | knowledge_retrieval_service, knowledge_ranker, knowledge_context_builder | M7 |
| `agents/` | orchestrator_service, router, registry, manifests, compose, context_builder, policy_engine, approval_service, run_recorder, task_service, agent_memory; `handlers/` (general, recall, specialist); `prompts/` (5 specialists); `tools/` (catalog, web_search, memory_read, doc_read) | M3–M8 |
| `search/` | provider (SearchProvider seam + DummySearchProvider), search_service | M8.5 |
| `identity/` | user_context | Phase 1.5 |

Worker tier (`app/workers/`): `embedding_worker`, `enrichment_worker` — async,
in-process, each job in an isolated retrying DB session, off the request path.

---

## 5. Agent workforce (verified in `manifests.py`)

| Key | Display name | Ceiling | Tier | Role |
| --- | --- | --- | --- | --- |
| `general` | Gummy (General) | GREEN | default | Conversational fallback / catch-all |
| `recall` | Memory Recall | GREEN | fast | Internal pipeline head (deterministic memory digest) |
| `career` | Career Agent | GREEN | default | Resumes, jobs, interviews, LinkedIn |
| `learning` | Learning Agent | GREEN | default | Teaching, study roadmaps, curricula |
| `planner` | Planner Agent | GREEN | default | Goals, milestones, timelines, schedules |
| `memory` | Memory Agent | GREEN | default | "What do you know about me" |
| `research` | Research Agent | GREEN | default | Compare/analyze/market/trends (web search arriving) |

**Routing:** deterministic weighted keyword scoring (`score_agents`, pure & free).
Phrase match = 2, single whole-word keyword = 1; highest score above threshold
wins, ties broken by `priority` then registry order. Below threshold → General.
Manual override bypasses scoring. Optional LLM fallback is opt-in (cost-gated).
`research` thread context triggers the `recall → general` pipeline.

**Orchestration shapes:** `single`, `pipeline` (scratch hand-off), `parallel`
(fan-out/gather, per-branch failure isolation). Every run writes a full A2A audit
trail (`agent_runs` / `agent_steps` / `agent_messages`) and is guarded by per-run
step and token-cost caps. An orchestrator error always falls back to the grounded
single-agent reply — routing never costs the user a reply.

---

## 6. Cross-cutting concerns

| Concern | Implementation |
| --- | --- |
| **Auth** | Supabase JWT (HS256/ES256 via JWKS) verified at the edge; per-request tenant context published before any DB write |
| **Tenant isolation** | Fail-closed Postgres Row-Level Security on every tenant table, keyed on a per-transaction GUC, run under a `NOSUPERUSER/NOBYPASSRLS` app role; `WITH CHECK` blocks cross-tenant writes |
| **Observability** | Langfuse (LLM/agent/retrieval/search traces), Sentry (errors + perf), PostHog (product analytics) — all best-effort / no-op when unconfigured |
| **Consent** | Memory extraction gated by consent mode (explicit / assisted / autonomous); provenance recorded per memory |
| **Search gating** | `is_search_eligible` restricts live search to Research/Career/Learning + recency cues + `web_search_enabled` |
| **Resilience** | SAVEPOINT degrade-to-empty for goals/files lookups; best-effort search/analytics never break a turn |

---

## 7. Frontend inventory (`frontend/src/`)

- **Framework:** Next.js 16.2, React 19.2, TypeScript 5, Tailwind 4, shadcn/Base UI.
- **State/data:** TanStack Query (server state), Zustand (UI store).
- **Auth:** Supabase SSR client + middleware proxy session.
- **Motion/brand:** framer-motion + react-three-fiber / three.js "Living Orb".
- **Analytics/monitoring:** posthog-js, @sentry/nextjs.
- **App routes:** workspace (chat), dashboard, memories, goals, files, agents,
  search, profile/settings, onboarding, welcome, auth (login/signup/reset),
  plus placeholder surfaces (automation, voice, future, updates, about).
- **Tests:** lightweight `node --test` unit tests for config/goals/dashboard logic.

> **Note:** several frontend surfaces (automation, voice) are intentionally inert
> placeholders representing planned phases — see §9 Technical Debt.

---

## 8. Test posture (verified run, 2026-06-24)

```
598 passed, 4 skipped, 22 warnings in ~32s
```

- **86 test files**, ~548 `def test_*` definitions (more cases via parametrization).
- **4 skipped:** all in `test_rls_postgres.py` — gated behind `RUN_RLS_PG_TESTS=1`
  + `RLS_TEST_DSN` (require a live Postgres `gummy_app` DSN; degrade-skip on SQLite).
- **Warnings:** benign `InsecureKeyLengthWarning` from short HMAC keys used in auth
  unit tests only (test fixtures, not production keys).
- Suite runs hermetically on in-memory SQLite; pgvector/full-text degrade to
  JSON/skip so the suite needs zero infra. See `docs/TEST_REPORT.md`.

---

## 9. Technical debt & known gaps (honest)

1. **Search is a seam, not a feature.** M8.5 ships `SearchProvider` + a
   `DummySearchProvider` and the eligibility gate; Brave (primary) / Tavily
   (fallback) are **not wired**. `web_search_enabled` defaults off.
2. **File RAG is keyword-only.** M6.5 retrieval is `ILIKE` term coverage, not
   vector ranking. `file_context_service` is the seam a vector retriever swaps under.
3. **In-process workers.** Embedding/enrichment run on asyncio in-process queues
   (no external broker). Designed to externalize to Redis/Celery but not yet done.
4. **Conversation-search N+1.** A per-hit conversation re-fetch in
   `conversation_search_service` (flagged in M4 notes) — batch before scale.
5. **Inert frontend surfaces.** `automation`, `voice` pages are placeholders for
   future phases; `future`/`updates`/`about` are informational.
6. **Synchronous file processing.** M6 extracts/chunks in-request; structured so a
   worker can take over without API change, but not yet moved off the request path.
7. **No image OCR / multimodal ingest.** Explicitly out of scope to date.
8. **Action layer is scaffolded.** `action_approvals` + policy engine + approval
   service exist (Green/Yellow/Red), but no real external actions are executed yet
   (that is Phase 5).
9. **Two duplicate-looking commits per milestone** in history (e.g. M6/M6.5/M8
   appear twice) — cosmetic git noise, not divergent code.

---

## 10. Risk register

| Risk | Severity | Mitigation status |
| --- | --- | --- |
| RLS regression on a new table | High | Each migration ships full RLS + grants; live PG-gated suite proves isolation (must be run in CI against Postgres) |
| Worker queue loss on restart (in-process) | Medium | Idempotent-ish consumers + watermark; externalize to durable queue before multi-process scale |
| LLM/provider cost runaway | Medium | Per-run step & token caps; deterministic free router; opt-in LLM fallback |
| Search spend when enabled | Low (off now) | Eligibility gate + per-call best-effort; disabled by default |
| Single-founder bus factor / context loss during pause | Medium | This freeze document set + master document preserve full context |

---

## 11. What is explicitly NOT built (freeze boundary)

- M9 Workflow Learning, M10 Automation Engine, M11 Multi-Agent Collaboration.
- Phase 5 Action & Execution (browser actions, tool-use framework, action agents).
- Any external action execution, scheduling, or live web search backend.

_This audit is the factual baseline; see `GUMMY_OS_MASTER_DOCUMENT.md` for the
narrative, architecture deep-dive, and roadmap built on top of it._
