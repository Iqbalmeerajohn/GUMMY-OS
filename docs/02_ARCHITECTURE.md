# 02 — Architecture

A layered, contract-first architecture. The frontend never talks to the database;
the API is a thin HTTP shell over services; services own business logic;
repositories own queries; workers run asynchronous, idempotent pipelines.

## Frontend architecture

```
src/
  app/                 # Next.js App Router routes
    (app)/             # Authenticated shell (header + bottom nav + orb)
      dashboard, memories, profile, settings, updates, future, search
    workspace/         # The chat workspace (history rail + chat pane + hub)
    (auth)/            # Login / signup / password flows
  components/          # Presentational + feature components
    workspace/         # ChatPane, Composer, HistoryRail, ConversationMenu, ...
    memory/            # MemoryCenter, MemoryCard, dialogs, transparency
    brand/             # LivingOrb / OrbScene (three.js), ambient background
  lib/
    api/               # client.ts (typed fetch) + resources.ts (endpoints)
    hooks/             # useChat, useDashboard, ...
    memory/            # query helpers, types, useMemory (TanStack Query)
    profile/           # profile hooks + display-name logic
  config/              # capability registry, release notes, memory config
```

Key decisions:
- **TanStack Query is the single source of truth for server state.** Memories,
  conversations, messages, and search all flow through query keys; mutations
  invalidate those keys rather than hand-managing local copies.
- **Streaming bypasses the JSON fetch wrapper.** `streamTurn` does a raw `fetch`
  with `Accept: text/event-stream`, parses SSE frames, and is cancellable via an
  `AbortController` owned by `ChatPane`.
- **The orb is the brand primitive**, rendered with three.js and downgraded
  under `prefers-reduced-motion`.

## Backend architecture

```
app/
  api/v1/        # Routers: conversations, memories, goals, tasks, actions, health
  schemas/       # Pydantic request/response contracts (the wire format)
  services/      # Business logic (conversation/, memory/, llm/, embeddings/, agents/)
  repositories/  # SQLAlchemy query construction + execution (pure builders, tested)
  models/        # ORM models
  workers/       # embedding_worker, enrichment_worker
  core/          # config, security (JWT), tenant_context, constants, exceptions
  database/      # session, base, Alembic migrations (0001–0018)
```

Principle: **routers are thin**. They resolve tenant + session, delegate to a
service, and shape the response. Query-construction helpers in repositories are
*pure* and compile-tested against the PostgreSQL dialect, so full-text / pgvector
SQL is validated without a live database.

## Memory architecture

Memory is a pipeline, not a table. See [03_MEMORY_SYSTEM.md](03_MEMORY_SYSTEM.md).
- `memories` (+ `memory_versions`, `memory_sources`) — the durable record and its provenance.
- `memory_embeddings` — pgvector vectors keyed by embedding model + content hash.
- `memory_extraction_service` — turns conversation turns into candidate memories.
- `search_repository` — tenant-scoped cosine-similarity ranking.

## Streaming architecture

1. Client POSTs to `/conversations/{id}/messages/stream`.
2. The turn service persists the user message, builds context (history + recalled
   memories), and streams model tokens back as SSE `delta` frames.
3. A terminal `done` frame carries the persisted assistant message id + the
   memories used to ground the reply.
4. The client renders a live bubble, then invalidates the message query so the
   persisted history seamlessly replaces the live text (no flicker, no duplicate).
5. Resilience: the stream is aborted on unmount and on conversation switch, and
   falls back to the non-streaming turn endpoint if the stream breaks mid-flight.

## Worker architecture

Workers are asynchronous, **tenant-aware**, and idempotent:
- **embedding_worker** — generates/updates embeddings for new memories and
  conversation summaries.
- **enrichment_worker** — post-processing of extracted memories.

Because Postgres RLS scopes every row to its owner, workers run inside an explicit
tenant context (`core/tenant_context.py`) so their queries pass the same policies
as request-path queries.

## Database architecture

PostgreSQL with the **pgvector** extension. 18 Alembic migrations build the schema
incrementally: memory core → soft delete → embeddings → recall tracking → **RLS** →
conversations → messages (with `seq`) → summaries + summary embeddings → memory
sources → extraction watermark → agents/runs/messages/steps/tool-invocations →
goals/tasks → action approvals. Tenant isolation is enforced in the database via
RLS, not only in application code.

## Agent architecture (scaffolded, not the M4 focus)

`services/agents/` contains the orchestrator, policy engine, context builder,
approval service, and handler stubs (general, recall). M4 routes through a general
path; the multi-agent expansion is future work and intentionally **not** enabled
as user-facing agents in this milestone.
