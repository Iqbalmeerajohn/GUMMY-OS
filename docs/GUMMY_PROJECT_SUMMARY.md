# GUMMY OS — Project Summary

> A solo-built, **memory-first, multi-tenant AI backend** — the foundation of a
> personal "AI operating system" of cooperating agents. Production-grade
> architecture: JWT auth, fail-closed Postgres Row-Level Security, pgvector semantic
> memory, and a persistent, memory-aware conversation system — all reused by future
> agents.

_One-line version:_ **Designed and built the backend for a multi-tenant, memory-first
AI assistant — FastAPI + PostgreSQL/pgvector with fail-closed Row-Level Security,
hybrid semantic retrieval, and an async memory-extraction pipeline — verified by 200+
automated tests.**

---

## Problem statement

Mainstream AI assistants are **stateless and forgetful** — they answer a question and
lose all context. They don't truly remember a user across sessions, can't safely
isolate one user's data from another's at the database layer, and offer no structured
path from "things you said in chat" to "durable knowledge the assistant acts on."

GUMMY OS tackles this with a **memory-first architecture**: every conversation both
*reads from* and *contributes to* a durable, per-user long-term memory, behind
strict tenant isolation — so the system becomes more useful the longer it's used,
while remaining private and safe to operate as multi-tenant SaaS. It is built to be
the shared substrate that specialized agents (career, learning, research, …) plug
into later.

---

## Architecture

A clean, layered, **stateless-service** backend over a stateful Postgres store.

```
Client ─(JWT)─▶ FastAPI ─▶ Services ─▶ Repositories ─▶ PostgreSQL (pgvector + RLS)
                  │           │              (flush)       ▲
                  │           └─ post-commit ─▶ async workers (embeddings, enrichment)
                  └─ per-request tenant context → per-transaction RLS GUC
```

- **HTTP layer** (FastAPI): thin; auth + request/response shaping only.
- **Service layer**: owns business logic and the transaction boundary; domain-split
  into *memory* and *conversation* services.
- **Repository layer**: pure persistence (build/run queries, `flush`, never commit) —
  no business logic, fully unit-testable.
- **Workers**: in-process asyncio queues run embedding and enrichment off the request
  path, each job in its own isolated DB session.
- **Database**: PostgreSQL (Supabase) with the `pgvector` extension (HNSW ANN index),
  GIN full-text indexes, and Row-Level Security on every tenant table.

**Engineering principles enforced throughout:** strict layering (no logic in routes,
no commits in repos), dependency-cycle-free module graph, provider abstractions for
LLM/embeddings, schema-validated I/O (no ORM leakage), and "scalable from day zero"
(multi-tenancy + horizontal-scale-friendly statelessness designed in from the start).

---

## Tech stack

| Area | Technology |
| --- | --- |
| **Language** | Python 3.12+ (fully type-annotated, `mypy`-clean) |
| **API** | FastAPI, Pydantic v2, pydantic-settings |
| **Data** | SQLAlchemy 2.0 (async) · Alembic migrations · asyncpg |
| **Database** | PostgreSQL (Supabase) · **pgvector** (HNSW cosine) · GIN full-text · **Row-Level Security** |
| **AI / LLM** | Anthropic **Claude** (gateway behind a provider protocol) |
| **Embeddings** | `sentence-transformers` (all-MiniLM-L6-v2, 384-dim); deterministic fake provider for tests |
| **Auth** | Supabase **JWT** (HS256) via PyJWT; per-request tenant context |
| **Async** | asyncio in-process workers (no external broker) |
| **Testing** | pytest, pytest-asyncio, httpx (ASGI), aiosqlite (hermetic suite) + Postgres-gated RLS/search tests |
| **Quality** | `ruff` (lint), `mypy` (types), `black` profile; CI-ready |
| **Packaging** | `uv` / `pyproject.toml`, Docker |

---

## Features (implemented)

**Long-term Memory Engine**
- Structured, categorized memories (profile, preference, career, learning, project,
  conversation, document) with importance + confidence scoring.
- **Semantic recall** via pgvector cosine search; **hybrid ranking** blending semantic
  similarity, importance, recency, and confidence.
- Memory **versioning** (immutable history) and **reinforcement** (recall makes a
  memory "stickier").
- Background embedding worker keeps vectors fresh without blocking requests.

**Conversation System**
- Persistent threads and messages; resume-anywhere (stateless backend, stateful store).
- **Memory-aware turn**: each reply is grounded in recent thread history + a rolling
  summary + retrieved long-term memories, assembled within a token budget.
- **Rolling conversation summaries** (versioned + embedded) keep long threads cheap to
  contextualize.
- **Conversation → memory extraction**: durable facts are distilled from chats and
  saved through the Memory Engine, **consent-gated**, with **provenance** links back
  to the source conversation.
- **Conversation search**: keyword (Postgres full-text) + semantic (summary
  embeddings) + a hybrid blend, with jump-to-message deep links.

**Platform**
- Multi-tenant from day one; JWT-authenticated; clean versioned REST API
  (`/api/v1/...`); 11 Alembic migrations; OpenAPI docs.

---

## Security

Security and privacy were treated as architecture, not an afterthought.

- **Fail-closed, database-enforced tenant isolation.** Row-Level Security on *every*
  tenant table; policies key off a **per-transaction Postgres GUC** set from the
  authenticated user. If the tenant is unset, queries return **zero rows** and inserts
  are rejected — isolation can't be bypassed by an application bug.
- **Non-bypass application role.** The app connects as a dedicated
  `NOSUPERUSER / NOBYPASSRLS` role so RLS actually applies (table owners/superusers
  bypass policies); the privileged connection is used only for migrations.
- **JWT verification at the edge.** HS256 Supabase tokens verified (signature +
  audience) before any DB work; the tenant is published to the request context *before*
  the user row is even upserted, so RLS covers that write too.
- **Defense in depth.** Queries are tenant-scoped in SQL *and* under RLS; `WITH CHECK`
  blocks cross-tenant inserts; a startup guard refuses to boot with the dev-auth
  bypass enabled in production.
- **Consent-based memory.** Automatic memory extraction is gated by a consent mode
  (explicit / assisted / autonomous); the default persists nothing automatically —
  "memory is earned, not assumed."
- **User-owned provenance.** Every extracted memory records where it came from, and
  durable memories survive deletion of their source chat (right-to-be-forgotten-friendly
  links).
- **Verified live**, not just asserted: a Postgres-gated test suite proves tenant
  isolation, fail-closed behavior, and cross-tenant rejection — including under
  full-text and vector search — running as the non-bypass role.

---

## Scale considerations

- **Stateless services + stateful store** → horizontal scale-out is trivial; any
  instance can serve any request, all durable state lives in Postgres.
- **Cheap context at scale.** Conversations are summarized (rolling summaries +
  embeddings) so long histories never replay into the model — bounding both latency
  and token cost.
- **Direct-column RLS on hot tables.** Tenant columns are denormalized onto
  high-volume tables (e.g. `messages`) so isolation is a cheap index-friendly compare,
  not a parent subquery.
- **Work off the request path.** Embedding generation and enrichment (titles,
  summaries, extraction) run in background workers with isolated, retrying sessions —
  the user's turn stays instant.
- **ANN + full-text indexing.** HNSW (pgvector) for semantic search and GIN for
  full-text keep retrieval fast as data grows.
- **Designed for the worker tier to externalize.** The in-process queue contract
  (isolated job sessions, idempotent-ish consumers) maps directly onto a shared queue
  (Redis/Celery) when multi-process scale-out is needed.

---

## Future roadmap

GUMMY OS is built as the **memory + conversation substrate** that specialized agents
stand on. With that foundation shipped, the roadmap layers capability:

- **Agent Framework / Master Orchestrator** — route intent to specialized agents that
  share the one memory store. (The turn service is already the insertion point;
  `tool` message roles, per-thread agent tags, and a shared provenance table are in
  place.)
- **Domain agents** — Career, Learning, Research, Builder, Daily Life — each owning a
  slice of the user's world, reading/writing the same consent-based memory.
- **Action layer** — a single audited choke point for external actions under a
  Green/Yellow/Red permission model (human-in-the-loop for high-impact actions).
- **Multimodal & platform** — vision, voice, browser automation, mobile.
- **Business tier** — multi-user organizations with shared, permissioned memory; an
  extensible agent ecosystem (the path from "personal JARVIS" to SaaS platform).

---

## Key engineering challenges solved

1. **Fail-closed multi-tenant isolation at the database layer.** Designed RLS keyed on
   a per-transaction GUC set from the JWT, run under a dedicated non-bypass role.
   Caught and fixed a real production-class gap during a live apply — table grants
   weren't propagating to migration-created tables — by making each migration ship the
   table's *full* access policy (RLS **and** grants), so security travels with the
   schema.

2. **Deterministic message ordering.** Tests surfaced that `created_at` is fixed per
   Postgres transaction (and second-resolution on SQLite), so messages appended
   together couldn't be reliably ordered. Introduced a monotonic per-conversation
   sequence (`UNIQUE(conversation_id, seq)`) as the insertion-faithful sort key.

3. **Conversation→memory extraction without duplicating the Memory Engine.** Routed
   every extracted fact through the existing memory service (reusing scoring,
   versioning, embedding) and added only provenance. Made it **consent-gated** and
   **watermark-first**, so the unit of work rolls back on LLM failure (retry) and never
   re-extracts on success (no duplicates).

4. **Enrichment off the request path.** Built an async worker (mirroring the embedding
   worker) that runs title generation, summarization, and extraction post-commit, each
   consumer in its own session — so the turn stays instant and one failing consumer is
   isolated and never crashes the worker or blocks the reply.

5. **Hybrid conversation search, tenant-isolated.** Combined Postgres full-text
   (`ts_rank`) with pgvector cosine over summary embeddings into a single blended
   ranking; compile-tested the generated SQL and **proved tenant isolation live** under
   the non-bypass role for both search paths.

6. **A hermetic, fast test strategy over Postgres-only features.** The full suite runs
   on in-memory SQLite (pgvector/full-text degrade to JSON/skip) for speed and zero
   infra, while a gated suite verifies RLS, FTS, and vector search against real
   Postgres — 200+ tests total, kept green across eight delivery milestones.

7. **Clean, scalable layering with zero dependency cycles.** Strict HTTP→service→repo→
   worker separation (no logic in routes, no commits in repos), provider abstractions
   for LLM/embeddings, and a deliberately acyclic module graph — so new agents and
   capabilities slot in without refactors.

---

## Résumé bullet variants

- Built a **multi-tenant AI backend** (FastAPI, PostgreSQL/pgvector, SQLAlchemy async)
  with **fail-closed Row-Level Security** enforcing per-user data isolation at the
  database layer, verified live by a Postgres-gated test suite.
- Engineered a **memory-first retrieval system** — hybrid semantic + keyword search
  (pgvector HNSW + Postgres full-text) with importance/recency/confidence ranking —
  powering memory-grounded, context-budgeted LLM responses.
- Designed a **consent-gated conversation→memory extraction pipeline** running on async
  background workers, reusing the core memory engine and writing full provenance, with
  a watermark for exactly-once-style processing.
- Delivered across **8 incremental milestones** with **200+ automated tests**,
  `ruff`/`mypy`-clean, 11 Alembic migrations, and live verification on Supabase
  Postgres.

## Interview talking points

- *"How do you guarantee one user can't read another's data?"* → Postgres RLS keyed on
  a per-transaction GUC, run under a non-bypass role, **fail-closed** — plus
  `WITH CHECK` on writes; verified by a live cross-tenant test suite.
- *"How do you keep an AI assistant cheap and coherent over long histories?"* → rolling
  summaries (versioned + embedded) + token-budgeted context assembly; the model never
  replays the full thread.
- *"How does chat become long-term memory safely?"* → consent-gated extraction routed
  through the existing memory engine (no duplicated logic), provenance-linked,
  watermark-first so failures retry and successes don't duplicate.
- *"How would this scale to many users?"* → stateless services, denormalized tenant
  columns for cheap RLS on hot tables, ANN + GIN indexing, and a worker contract that
  externalizes to a shared queue.

---

_Companion docs: [VISION.md](VISION.md) · [ROADMAP.md](ROADMAP.md) ·
[PHASE2_ARCHITECTURE.md](PHASE2_ARCHITECTURE.md) (as-built architecture) ·
[../architecture/](../architecture/) (design specs)._
