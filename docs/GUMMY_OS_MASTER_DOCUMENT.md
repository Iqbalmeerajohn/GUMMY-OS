# GUMMY OS — Master Document

> **The single canonical record of GUMMY OS** at the M8.5 development-freeze point
> (2026-06-24). Self-contained: complete history, every architecture layer, test
> results, résumé positioning, technical debt, and the roadmap through Phase 9.
> Companion freeze docs: `PROJECT_AUDIT.md`, `GUMMY_OS_STORY.md`,
> `GUMMY_OS_ARCHITECTURE.md`, `TEST_REPORT.md`, `PRODUCT_OVERVIEW.md`,
> `RESUME_PROJECT_SUMMARY.md`, `FUTURE_ROADMAP.md`.

---

## Table of contents

1. [Complete history](#1-complete-history)
2. [Phase-by-phase breakdown](#2-phase-by-phase-breakdown)
3. [Technical architecture](#3-technical-architecture)
4. [Product architecture](#4-product-architecture)
5. [Database architecture](#5-database-architecture)
6. [API architecture](#6-api-architecture)
7. [Agent architecture](#7-agent-architecture)
8. [Knowledge architecture](#8-knowledge-architecture)
9. [Search architecture](#9-search-architecture)
10. [Deployment architecture](#10-deployment-architecture)
11. [Test results](#11-test-results)
12. [Résumé positioning](#12-résumé-positioning)
13. [Interview talking points](#13-interview-talking-points)
14. [Technical debt](#14-technical-debt)
15. [Future roadmap through Phase 9](#15-future-roadmap-through-phase-9)

---

## Executive summary

**GUMMY OS** is a personal, memory-first AI operating system. An assistant named
**Gummy** learns the user over time and routes requests to a team of specialized
agents (career, learning, planner, memory, research), all grounded in a private,
consent-based long-term memory behind fail-closed multi-tenant isolation.

At the freeze point it is a working, tested system: **598 passing backend tests**
(0 failing), 21 database migrations, ~55 REST endpoints, 7 agent manifests, a
streaming Next.js/React web client, and full observability — built solo across 9
milestones. Active development is paused; this document preserves complete context
for a clean restart at M9.

| Snapshot | Value |
| --- | --- |
| Freeze milestone | M8.5 — Search Layer (seam) |
| Phases complete | 0, 1, 1.5, 2, 3; Phase 4 partial (M7, M8, M8.5) |
| Tests | 598 passed / 0 failed / 4 Postgres-gated skips |
| Stack | Python 3.12 · FastAPI · SQLAlchemy 2.0 async · PostgreSQL/pgvector · Next.js 16 / React 19 |

---

## 1. Complete history

GUMMY OS began as a rebrand of *IQBAL OS* and a deliberate, documentation-first
foundation: vision, design system, conventions, architecture specs, and ADRs were
written before application code. From there it advanced through nine milestones,
each shipped green and verified:

| # | Milestone | Theme |
| --- | --- | --- |
| Phase 0 | Foundation & Rebranding | Vision, design system, ADRs, repo structure |
| M-series early | M0.5–M4 | Brand/Living Orb, auth UI, onboarding, workspace, Memory Center |
| Phase 1 | Memory Engine | Storage, versioning, embeddings, hybrid recall, RLS |
| Phase 1.5 | Auth & Security | JWT, tenant context, fail-closed RLS |
| Phase 2 | Conversation Engine | Turns, summaries, extraction, conversation search |
| M5 / M5.5 | Goals & Goal Intelligence | Goals, milestones, tasks, extraction |
| M6 / M6.5 | Files & File Intelligence | Upload→extract→chunk→retrieve, file-aware chat |
| M7 | Unified Knowledge Engine | One ranked, compressed grounding seam |
| M8 | Multi-Agent Workforce | Deterministic router + 5 specialists |
| M8.5 | Search Layer | `SearchProvider` seam + eligibility gating (freeze) |

Git history confirms the arc: `…M4 → M5 goals → M6/6.5 files → M7 knowledge →
M8 multi-agent → M8 polish + M8.5 search` (latest `eedcedf`). Full narrative in
`GUMMY_OS_STORY.md`.

---

## 2. Phase-by-phase breakdown

**Phase 0 — Foundation & Rebranding ✅** — IQBAL OS → GUMMY OS; architecture,
design system, conventions, ADRs (tech stack, memory-first, PostgreSQL/pgvector,
FastAPI), repo structure.

**Phase 1 — Memory Engine ✅** — categorized memories with importance/confidence;
pgvector semantic recall; hybrid ranking (similarity + importance + recency +
confidence); immutable versioning; reinforcement; background embedding worker.

**Phase 1.5 — Authentication & Security ✅** — Supabase JWT verified at the edge;
per-request tenant context; fail-closed Postgres RLS under a non-bypass role.

**Phase 2 — Conversation Engine ✅** — persistent threads; memory-aware turn
(history + rolling summary + retrieved memories, token-budgeted); rolling
summaries (versioned + embedded); consent-gated, watermark-first chat→memory
extraction with provenance; hybrid conversation search.

**Phase 3 — Core Intelligence ✅**
- *M4* — streaming workspace, Memory Center, conversation management, unified search.
- *M5 / M5.5* — goals, milestones, tasks, progress, conversational goal extraction.
- *M6 / M6.5* — files upload/extract/chunk/retrieve; file-aware chat (keyword RAG)
  + chat attachments.

**Phase 4 — Knowledge & Agent Workforce 🟡 (freeze here)**
- *M7* — unified knowledge retrieval, ranker, compressor; single-retrieval rule.
- *M8* — deterministic router; Career/Learning/Planner/Memory/Research specialists;
  A2A trace; routing diagnostics.
- *M8.5* — `SearchProvider` seam + eligibility gating (Brave/Tavily not wired).
- *M9–M11* — Workflow Learning, Automation, Multi-Agent Collaboration — **planned**.

---

## 3. Technical architecture

Layered, stateless-service backend over a stateful Postgres store:

```
Client ─(JWT)─▶ FastAPI ─▶ Services ─▶ Repositories ─▶ PostgreSQL (pgvector + RLS)
                  │           ├─ Orchestrator ─▶ Agents ─▶ M7 Knowledge seam
                  │           └─ post-commit ─▶ async workers (embeddings, enrichment)
                  └─ per-request tenant context → per-transaction RLS GUC
```

**Layering contract:** HTTP (auth + shaping) → Service (logic + transaction
boundary) → Repository (queries + `flush`, never commit) → Worker (isolated
off-request jobs). Principles: no logic in routes, no commits in repos, provider
abstractions (LLM/embeddings/storage/search), schema-validated I/O, acyclic module
graph, multi-tenancy designed in from day zero. Full detail:
`GUMMY_OS_ARCHITECTURE.md §1`.

---

## 4. Product architecture

Gummy is a single conversational surface backed by a team of agents and a memory
spine. Product pillars: **memory that compounds**, **a team not a chatbot**,
**consent and control**. User-facing capabilities at freeze: streaming chat
workspace with agent selection, Memory Center (view/edit/delete with provenance),
Goals (with chat extraction), Files (upload + attachments + keyword Q&A), unified
search, profile/settings, dashboard. Full detail: `PRODUCT_OVERVIEW.md`.

Frontend: Next.js 16 App Router, React 19, Tailwind 4, shadcn/Base UI, TanStack
Query (server state), Zustand (UI), Supabase SSR auth, framer-motion +
react-three-fiber "Living Orb", posthog-js + @sentry/nextjs.

---

## 5. Database architecture

**Engine:** PostgreSQL (Supabase) + pgvector (HNSW cosine) + GIN full-text.
**ORM:** SQLAlchemy 2.0 async. **Migrations:** 21 Alembic revisions (`0001`→`0021`).

**Tables by domain:** memory (`memories`, `memory_versions`, `memory_embeddings`,
`memory_sources`); conversation (`conversations`, `messages` with monotonic `seq`,
`conversation_summaries`, `conversation_summary_embeddings`); agents (`agents`,
`agent_runs`, `agent_steps`, `agent_messages`, `tool_invocations`); goals
(`goals`, `goal_milestones`, `tasks`); files (`files`, `file_chunks` cascade);
actions (`action_approvals`); identity (`users`).

**Every tenant table:** denormalized `user_id` (cheap direct-column RLS),
fail-closed RLS + `WITH CHECK`, the `gummy_app` grant shipped inside the migration
(security travels with schema), CHECK constraints on status enums. Full migration
list: `PROJECT_AUDIT.md §3.4`.

---

## 6. API architecture

REST under `/api/v1`, OpenAPI-documented, ~55 endpoints across 10 routers
(`memories` 11, `conversations` 10, `goals` 11, `milestones` 2, `tasks` 4,
`actions` 4, `files` 6, `knowledge` 1, `agents` 2, `health` 4).

Key surface: `POST /conversations/{id}/messages` and `…/stream` (optional `agent`
override + `attachment_file_ids`); `GET /agents` and `/agents/diagnostics`;
`POST /files/upload`; `GET /memories/search`; `GET /knowledge`; `GET /health[/ready|/llm]`.
Conventions: versioned path, tenant-scoped (foreign → `404`), Pydantic v2 models,
SSE streaming with non-streaming fallback. Full detail: `GUMMY_OS_ARCHITECTURE.md §3`.

---

## 7. Agent architecture

```
turn → Router (deterministic keyword scoring) → Orchestrator
        → plan: single | pipeline | parallel
        → context_builder → M7 Knowledge seam
        → handlers.dispatch (general | recall | specialist)
        → run_recorder → agent_runs/steps/messages (A2A trace) + _RunGuard caps
        → compose → reply (+ proposed actions/memories/citations)
   Langfuse: agent.route / agent.execute / agent.response
```

**7 manifests:** general (catch-all), recall (internal pipeline head), and 5
specialists — career, learning, planner, memory, research (all GREEN ceiling,
tool-less, LLM-backed, grounded only through M7). Code is the source of truth for
identity; the `agents` table holds only `enabled` runtime state.

**Router:** weighted keyword scoring (phrase=2, word=1, word-boundary), highest
above threshold wins, ties by `priority` then registry order, below threshold →
General; manual override bypasses; optional cost-gated LLM fallback; `research`
thread → `recall→general` pipeline. Pure & free, so diagnostics explains live routing.

**Reliability:** per-run step + token-cost caps; orchestrator always falls back to
the grounded single-agent reply — routing never costs a reply. **Action seam:**
`policy_engine` + `approval_service` + `action_approvals` implement Green/Yellow/Red
(human-in-the-loop), ready for Phase 5. Full detail: `GUMMY_OS_ARCHITECTURE.md §4`.

---

## 8. Knowledge architecture

M7's single grounding seam: `context_from_pack → knowledge_ranker → compressor`.
`knowledge_retrieval_service` gathers candidates across memories, conversation
summaries, goals, and files; `knowledge_ranker` produces one unified ranking;
`knowledge_context_builder` compresses the top results into a token-budgeted
context pack. **Rule #1 — single retrieval layer:** no agent retrieves on its own,
so retrieval logic, cost, and tenant-scoping live in exactly one place.

---

## 9. Search architecture

M8.5 ships the **seam only**:

```
maybe_search(agent_key, query):
  gate: web_search_enabled ∧ agent∈{research,career,learning} ∧ (recency cue ∨ year≥2024)
  → get_provider() : SearchProvider  (DummySearchProvider ships; Brave/Tavily planned)
  → normalize → dedupe → rank → limit → SearchResult[]
```

Best-effort by contract (returns `[]`, never raises — an outage never costs a
reply). `set_provider` swaps the backend without touching agents. **Disabled by
default** at freeze.

---

## 10. Deployment architecture

| Concern | Choice |
| --- | --- |
| Backend | FastAPI/Uvicorn (ASGI), Docker, Railway-style container |
| Database | Supabase PostgreSQL + pgvector; Alembic migrations on deploy (privileged role) |
| Frontend | Next.js 16 (Vercel-style), Supabase SSR auth |
| Embeddings | OpenAI hosted by default (no torch); local HF optional (`--extra embeddings`) |
| File storage | `LocalFileStorage` today; `supabase`/`s3`/`r2` at one factory |
| Config | pydantic-settings + `.env`; startup guards on unsafe prod config |
| Scale path | Stateless services scale out; in-process workers map to Redis/Celery; ANN + GIN keep retrieval fast |

---

## 11. Test results

```
598 passed, 4 skipped, 22 warnings in ~32s   (PYTEST_EXIT=0)
```

- **0 failures.** 86 test files, ~548 `test_*` definitions.
- **4 skips:** all `test_rls_postgres.py`, Postgres-gated (`RUN_RLS_PG_TESTS=1` +
  `RLS_TEST_DSN`) — verify fail-closed RLS, cross-tenant rejection, and isolation
  under FTS + vector search as the non-bypass role.
- **22 warnings:** benign short-HMAC-key warnings from auth *unit tests* only.
- **Strategy:** hermetic in-memory SQLite (Postgres-only features degrade
  gracefully) + a Postgres-gated security suite; LLM/embeddings behind
  deterministic fakes. Full detail: `TEST_REPORT.md`.

---

## 12. Résumé positioning

**Headline:** *Designed and built a multi-tenant, memory-first AI operating system
— FastAPI + PostgreSQL/pgvector with fail-closed Row-Level Security, a unified
semantic-retrieval knowledge layer, and a routed multi-agent workforce — verified
by ~600 automated tests across 9 milestones.*

Top bullets:
- Multi-tenant AI backend with **fail-closed Postgres RLS** verified live under a
  non-bypass role.
- **Memory-first hybrid retrieval** (pgvector HNSW + full-text, importance/recency
  ranking) for grounded, token-budgeted LLM responses.
- **Multi-agent orchestration runtime** (deterministic router; single/pipeline/
  parallel; step + cost guards; guaranteed fallback; A2A trace).
- **9 milestones, 598 tests, 21 migrations**, `ruff`/`mypy`-clean — solo.

Full set + LinkedIn blurb + honesty guardrails: `RESUME_PROJECT_SUMMARY.md`.

---

## 13. Interview talking points

- **Tenant isolation** → Postgres RLS on a per-transaction GUC, non-bypass role,
  fail-closed, `WITH CHECK`; each migration ships RLS *and* grants so security
  travels with the schema; proven by a live cross-tenant suite.
- **Cheap long histories** → rolling summaries (versioned + embedded) + token-
  budgeted assembly; the model never replays the thread.
- **Chat → memory safely** → consent-gated, watermark-first extraction through the
  existing engine; failure rolls back & retries, success never duplicates.
- **Reliable multi-agent routing** → deterministic free scoring + graceful
  degradation + guaranteed orchestrator fallback + per-run caps.
- **Single retrieval layer** → five specialists, one grounding seam; retrieval cost
  and scoping in one place.
- **Scale** → stateless services, denormalized tenant columns, ANN + GIN, worker
  contract that externalizes to a queue.

Expanded Q→A: `RESUME_PROJECT_SUMMARY.md §5`.

---

## 14. Technical debt

1. **Search is a seam** — Brave/Tavily not wired; `web_search_enabled` off.
2. **File RAG is keyword-only** — vector retriever swaps under `file_context_service`.
3. **In-process workers** — externalize to Redis/Celery for multi-process scale.
4. **Conversation-search N+1** — batch the per-hit re-fetch before scale.
5. **Synchronous file processing** — move off the request path (worker-ready).
6. **Inert frontend surfaces** — automation/voice are placeholders.
7. **Action layer scaffolded, not executing** — Phase 5 wires real actions.
8. **No image OCR / multimodal ingest** — out of scope to date.
9. **Add a Postgres CI stage** — run the RLS-gated suite on every change.

Severity/risk table: `PROJECT_AUDIT.md §9–10`.

---

## 15. Future roadmap through Phase 9

| Phase | Milestones | Status |
| --- | --- | --- |
| 4 (remaining) | M9 Workflow Learning, M10 Automation Engine, M11 Multi-Agent Collaboration | ⏸ planned |
| 5 | M12 Browser Actions, M13 Tool-Use Framework, M14 Action Agents, M15 HITL Approvals | 🔮 |
| 6 | M16 Personal Workforce, M17 Knowledge Graph, M18 Predictive Intelligence, M19 Life OS | 🔮 |
| 7 | M20 Multi-Tenant SaaS, M21 Team Workspaces, M22 Shared Memory, M23 Org Agents, M24/M25 Marketplaces | 🔮 |
| 8 | Enterprise memory/workflows/agents, governance, compliance, audit | 🔮 |
| 9 | Personal/Team/Enterprise AI OS, Agent + Workflow marketplaces, Developer + API platform | 🔮 |

**Restart sequence:** re-baseline (pytest/ruff/mypy) → wire live search into the
M8.5 seam → **M9 Workflow Learning** (extend memory + knowledge, no new retrieval
layer) → M10 Automation (bring a durable worker queue) → M11 Collaboration (richer
orchestrator plans + synthesis). Many later phases are *productization of an
already-multi-tenant, already-scaffolded system*, not rewrites. Full detail:
`FUTURE_ROADMAP.md`.

---

## Final note

The freeze is a clean checkpoint: the substrate (memory + conversation + knowledge
+ agents) is built and tested, the workforce has started, and the execution layer
is designed and scaffolded. Development is paused — not abandoned — and this
document set preserves everything needed to resume at M9 with confidence.

_— GUMMY OS Master Document, M8.5 freeze, 2026-06-24._
