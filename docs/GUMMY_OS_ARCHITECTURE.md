# GUMMY OS — Technical Architecture

> As-built architecture at the M8.5 freeze point (2026-06-24). Covers system,
> data, API, agent, knowledge, search, security, and deployment layers. Verified
> against the backend tree; companion to `architecture/` design specs and
> `PROJECT_AUDIT.md`.

---

## 1. System architecture

A clean, layered, **stateless-service** backend over a stateful Postgres store.

```
Client ─(JWT)─▶ FastAPI ─▶ Services ─▶ Repositories ─▶ PostgreSQL (pgvector + RLS)
                  │           │              (flush)          ▲
                  │           ├─ Orchestrator ─▶ Agents ─▶ M7 Knowledge seam
                  │           └─ post-commit ─▶ async workers (embeddings, enrichment)
                  └─ per-request tenant context → per-transaction RLS GUC
```

**Layering contract (enforced):**

| Layer | Responsibility | Forbidden |
| --- | --- | --- |
| **HTTP** (`api/`) | Auth, request/response shaping, dependency wiring | Business logic |
| **Service** (`services/`) | Business logic, owns the transaction boundary | Direct SQL construction |
| **Repository** (`repositories/`) | Build/run queries, `flush` | `commit`, business logic |
| **Worker** (`workers/`) | Off-request jobs, isolated sessions | Touching the request session |

Principles: no logic in routes, no commits in repos, provider abstractions for
LLM/embeddings/storage/search, schema-validated I/O (no ORM leakage to the edge),
a deliberately **acyclic module graph**, and "scalable from day zero"
(multi-tenancy + stateless services designed in from the start).

---

## 2. Data architecture

**Engine:** PostgreSQL (Supabase) + `pgvector` (HNSW cosine ANN) + GIN full-text.
**Migrations:** 21 Alembic revisions (`0001`→`0021`). **ORM:** SQLAlchemy 2.0 async.

### Core tables (by domain)

- **Memory:** `memories`, `memory_versions` (immutable history),
  `memory_embeddings` (vector), `memory_sources` (provenance).
- **Conversation:** `conversations`, `messages` (monotonic `seq`),
  `conversation_summaries`, `conversation_summary_embeddings`.
- **Agents:** `agents` (runtime state), `agent_runs`, `agent_steps`,
  `agent_messages` (A2A trace), `tool_invocations`.
- **Goals:** `goals`, `goal_milestones`, `tasks`.
- **Files:** `files`, `file_chunks` (`ON DELETE CASCADE`).
- **Actions:** `action_approvals` (Green/Yellow/Red choke point).
- **Identity:** `users`.

### Conventions on every tenant table

1. Denormalized `user_id` (direct-column RLS — cheap, index-friendly compares
   on hot tables like `messages`, not parent subqueries).
2. Fail-closed **RLS** policy + `WITH CHECK` on writes.
3. The conditional `gummy_app` role grant **shipped inside the migration** — so
   access policy travels with the schema and can't drift.
4. CHECK constraints on status enums.

---

## 3. API architecture

REST under `/api/v1`, OpenAPI-documented, ~55 endpoints across 10 routers
(`memories`, `conversations`, `goals`, `milestones`, `tasks`, `actions`, `files`,
`knowledge`, `agents`, `health`). Representative surface:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/conversations/{id}/messages` | One turn (optional `agent` override, `attachment_file_ids`) |
| POST | `/conversations/{id}/messages/stream` | SSE token streaming; `done` event carries the answering agent |
| GET | `/agents` | List selectable agents (General + 5 specialists) |
| GET | `/agents/diagnostics?q=` | Explain routing for a query (read-only) |
| POST | `/files/upload` | Upload → extract → chunk (multipart) |
| GET | `/memories/search` | Semantic + keyword memory recall |
| GET | `/knowledge` | Unified retrieval diagnostics |
| GET | `/health`, `/health/ready`, `/health/llm` | Liveness / readiness / provider probes |

**Conventions:** versioned path; tenant-scoped (foreign → `404`, never `403`);
Pydantic v2 request/response models; streaming via SSE with a graceful fallback to
the non-streaming endpoint.

---

## 4. Agent architecture

```
turn → Router (deterministic) → Orchestrator → plan(single|pipeline|parallel)
        │                          │
        │                          ├─ context_builder → M7 Knowledge seam
        │                          ├─ handlers.dispatch (general | recall | specialist)
        │                          ├─ run_recorder → agent_runs/steps/messages (A2A trace)
        │                          ├─ _RunGuard (step + token-cost caps)
        │                          └─ compose → reply (+ proposed actions/memories/citations)
        └─ Langfuse spans: agent.route / agent.execute / agent.response
```

- **Registry + manifests:** code is the source of truth for agent identity and
  capability (`manifests.py`); the `agents` table carries only runtime `enabled`
  state, re-seeded idempotently at startup. 7 built-ins (see `PROJECT_AUDIT.md §5`).
- **Router:** weighted keyword scoring (`score_agents`, pure & free) — phrase=2,
  word=1, word-boundary matching; highest above `AGENT_ROUTER_MIN_SCORE` wins,
  ties by `priority` then registry order; manual override bypasses; optional
  cost-gated LLM fallback; `research` thread → `recall→general` pipeline.
- **Handlers:** `general` (wraps the proven Phase 2 grounded-reply core), `recall`
  (deterministic memory digest, no LLM), `specialist` (shared handler; all five
  specialists ground **only** through the M7 seam — the single-retrieval rule).
- **Plan shapes:** `single`; `pipeline` (scratch handed step→step); `parallel`
  (fan-out/gather, per-branch failure isolation, succeeds if ≥1 branch does). DB
  writes stay sequential on the turn session; only pure handlers run concurrently.
- **Reliability:** per-run step & token caps halt runaway plans; `run_turn` wraps
  `orchestrate` with a guaranteed fallback to `generate_grounded_reply` — an
  orchestrator error never costs the user a reply.
- **Action seam:** `policy_engine` + `approval_service` + `action_approvals`
  implement the Green/Yellow/Red permission model (human-in-the-loop), ready for
  Phase 5 execution.

---

## 5. Knowledge architecture (M7)

A single grounding seam: `context_from_pack → knowledge_ranker → compressor`.

- **`knowledge_retrieval_service`** gathers candidates across sources (memories,
  conversation summaries, goals, files) for a query.
- **`knowledge_ranker`** scores and orders them into one unified ranking.
- **`knowledge_context_builder`** compresses the top results into a token-budgeted
  context pack consumed by the prompt builder / specialist handler.

**Rule #1 — single retrieval layer:** no agent performs its own retrieval; every
agent grounds through this seam, so retrieval logic, cost, and tenant-scoping live
in exactly one place.

---

## 6. Search architecture (M8.5 — seam)

```
reply path → search_service.maybe_search(agent_key, query)
   ├─ is_search_eligible:  web_search_enabled  ∧  agent∈{research,career,learning}
   │                        ∧  (recency/lookup cue ∨ year≥2024)
   ├─ get_provider() → SearchProvider Protocol
   │     · DummySearchProvider (offline)  · TavilySearchProvider (live, keyed)
   └─ normalize → dedupe (url, domain+title) → rank → limit  → SearchResult[]
```

Best-effort by contract: every entrypoint returns `[]` rather than raising, so a
search outage never costs a reply. `set_provider` swaps the backend without
touching agents. **Disabled by default** (`web_search_enabled` off) at the freeze.

---

## 7. Security architecture

| Control | Detail |
| --- | --- |
| **JWT at the edge** | Supabase HS256/ES256 (JWKS) verified — signature + audience — before any DB work |
| **Tenant context first** | Published to request context *before* the user row is upserted, so RLS covers that write too |
| **Fail-closed RLS** | Per-transaction GUC policy on every tenant table; unset tenant → zero rows / rejected inserts |
| **Non-bypass role** | App connects as `NOSUPERUSER/NOBYPASSRLS` `gummy_app`; privileged role only for migrations |
| **Defense in depth** | Tenant-scoped in SQL *and* under RLS; `WITH CHECK` on writes; startup guard refuses dev-auth bypass in production |
| **Consent** | Memory extraction gated (explicit/assisted/autonomous); default persists nothing automatically |
| **Provenance** | Every extracted memory records its source; durable memories survive source-chat deletion |
| **Verified live** | Postgres-gated suite proves isolation, fail-closed behavior, and cross-tenant rejection under the non-bypass role — including under FTS and vector search |

---

## 8. Observability architecture

- **Langfuse** — LLM/agent/retrieval/search traces: `agent.route/execute/response`,
  `file.upload/process/chunk/search`, `search.query/rank/summarize`. No-op unless keyed.
- **Sentry** — error + performance tracing (FastAPI/asyncio); processing failures
  captured with component tags.
- **PostHog** — product analytics: agent routing events (`AgentSelected/Executed/
  Fallback/Override`), search events, file lifecycle events. Best-effort; degrades
  to structured logs when disabled — analytics never breaks a turn.

---

## 9. Deployment architecture

| Concern | Choice |
| --- | --- |
| **Backend** | FastAPI / Uvicorn (ASGI); Docker; Railway-style container target |
| **Database** | Supabase PostgreSQL + pgvector; Alembic migrations on deploy (privileged role) |
| **Frontend** | Next.js 16 (Vercel-style target); Supabase SSR auth |
| **Embeddings** | OpenAI hosted API by default (no torch/CUDA); local HF provider optional (`--extra embeddings`) |
| **File storage** | `LocalFileStorage` today (`FILES_STORAGE_DIR`); `supabase`/`s3`/`r2` plug in at one factory |
| **Config** | pydantic-settings; `.env` (see `.env.example`); startup guards on unsafe prod config |
| **Scale path** | Stateless services scale horizontally; in-process worker contract maps onto Redis/Celery; ANN + GIN keep retrieval fast |

---

## 10. Frontend architecture

Next.js 16 App Router + React 19, TypeScript, Tailwind 4, shadcn/Base UI.
TanStack Query for server state (deduped query keys; cached conversation
switching), Zustand for UI state, Supabase SSR for auth. Brand layer: framer-motion
+ react-three-fiber "Living Orb". Streaming chat via SSE with `AbortController`
cancellation and a non-streaming fallback. Analytics (posthog-js) + monitoring
(@sentry/nextjs) wired through provider components.

---

## 11. Architectural invariants (the rules that held)

1. **Memory is the spine** — every domain plugs into one memory store.
2. **Single retrieval layer** — agents never retrieve on their own (M7 seam).
3. **Fail-closed isolation** — RLS + non-bypass role; security travels with schema.
4. **Routing never fails a request** — deterministic scoring + guaranteed fallback.
5. **Best-effort side channels** — search/analytics/enrichment never break a turn.
6. **No commits in repositories** — the service owns the transaction boundary.
7. **Acyclic module graph** — new agents/capabilities slot in without refactors.
