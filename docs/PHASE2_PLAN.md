# GUMMY OS — Phase 2 Plan: Conversation System

> **Status: Design / planning only.** No implementation until this plan is reviewed and
> approved. Phase 1 (`phase1-complete`) and Phase 1.5 (`phase1.5-complete`) are frozen and
> must not be modified. This document plans the **Conversation System** and its integration
> with the existing **Memory Engine**, **JWT auth**, and **RLS** infrastructure.

Related design docs (Phase 0, authoritative for intent):
[conversation-system.md](../architecture/conversation-system.md) ·
[memory-system.md](../architecture/memory-system.md) ·
[agent-framework.md](../architecture/agent-framework.md) ·
[security-system.md](../architecture/security-system.md) ·
[database-design.md](../architecture/database-design.md)

---

## 0. Repository State at Phase 2 Start (verified 2026-06-08)

| Aspect | State |
| --- | --- |
| **Branch** | `main`, clean, up to date with `origin/main`. Feature branch `feat/phase1.5-jwt-auth` merged. |
| **Tags** | `phase1-complete`, `phase1.5-complete` present. Phase 1.5 is the latest sealed milestone. |
| **Migration head** | `0005_enable_rls` (single head, linear chain `0001→0005`). Phase 2 begins at `0006`. |
| **Tests** | `106 passed, 1 skipped` via `.venv` pytest. Green baseline. |
| **Last commits** | RLS hardening + runtime switch to non-bypass `gummy_app` role (enforcement active). |

### Architecture state inherited (the reuse surface)

These are **load-bearing seams Phase 2 builds on, not rebuilds**:

- **Models** — `Base` + `UUIDPrimaryKeyMixin` (app- & DB-side `gen_random_uuid()`),
  `TimestampMixin` (`created_at`/`updated_at`), `CreatedAtMixin` (append-only rows).
  Deterministic constraint naming convention in [base.py](../backend/app/database/base.py).
- **Enums** — string-backed (`native_enum=False`) via `enum_type()`, value integrity by
  explicit named CHECK constraints. `MemoryCategory` **already includes `conversation`** —
  the promotion target for distilled chat memory exists today.
- **Repositories** — module-level async functions (not classes). Pure persistence:
  build/run queries, mutate ORM, `flush()` — **never commit** (the service owns the unit of
  work), no business logic. Pattern: [memory_repository.py](../backend/app/repositories/memory_repository.py).
- **Services** — module-level async functions. The memory-aware chat pipeline today is
  `retrieve → assemble_context → build_prompt → llm.generate`, **stateless** (no
  persistence of turns): [chat_service.py](../backend/app/services/memory/chat_service.py).
- **Retrieval** — `memory_retrieval_service` (hybrid: vector + metadata + FTS, ranked) and
  `context_assembly_service` (pure, token-budgeted, dedupe). Both reused unchanged.
- **Embeddings** — `EmbeddingService` with provider `base`/`factory`/`fake`/`huggingface`,
  a separate `memory_embeddings` table (pgvector), and an `embedding_worker` async-sync
  pattern. Reused for message/summary embeddings.
- **LLM** — `claude_gateway` behind `LLMProvider` base + `factory` + `fake` provider.
- **Auth + tenancy** — Supabase JWT (HS256) verification → `CurrentUser`; request-scoped
  `ContextVar` ([tenant_context.py](../backend/app/core/tenant_context.py)) → per-transaction
  GUC `app.current_user_id` set in the `after_begin` hook; cleared per request.
- **RLS** — every tenant table has `ENABLE ROW LEVEL SECURITY` + a `*_tenant_isolation`
  policy keyed on `NULLIF(current_setting('app.current_user_id', true), '')::uuid`
  (**fail-closed**: unset tenant ⇒ NULL ⇒ no rows). App runs as non-bypass `gummy_app`.
  Pattern: [0005_enable_rls.py](../backend/app/database/migrations/versions/0005_enable_rls.py).

> **Design rule for Phase 2:** every new table and code path must conform to these five
> seams. If a design choice would force a change to a frozen seam, it is the wrong choice.

---

## 1. Goals of Phase 2

Phase 2 turns the **stateless** memory-aware chat pipeline into a **persistent,
thread-based Conversation System** that is the raw-material feedstock for the Memory Engine.

**Primary goals**

1. **Persist conversations and messages** — durable, tenant-scoped threads of
   user/assistant/system/tool turns; resume-where-you-left-off across sessions/devices.
2. **Scalable per-thread context** — rolling summaries so long threads never replay the full
   history into the model (cost + latency control).
3. **Conversation → Memory pipeline** — extract durable facts from conversations and propose
   them as long-term memories through the **existing** consent-gated Memory Engine. Reuse the
   `conversation` memory category and the existing scoring/dedupe/embedding path.
4. **Two-layer context retrieval** — per turn, assemble: recent thread messages + thread
   rolling summary + cross-thread long-term memories (existing hybrid retrieval).
5. **Conversation search** — keyword (Postgres FTS over messages) + semantic (over embedded
   conversation summaries).
6. **Full RLS + JWT continuity** — new tables obey the same fail-closed GUC tenant policy; no
   new auth surface.

**Non-goals (explicitly deferred)**

- No Agent Framework / Master Orchestrator implementation (Phase 2 leaves clean seams only).
- No multi-agent routing, no tool execution, no Action Agent / permission tiers.
- No document ingestion pipeline (Document Memory stays Phase 3+).
- No frontend build (API + service + repo layers only; the existing `frontend/` is untouched).
- No streaming responses (can be layered later; the persistence model is stream-ready).

**Exit criteria**

- Migrations `0006…` apply cleanly forward **and** downgrade; head advances; RLS enabled on
  all new tables and proven by an integration test under the `gummy_app` role.
- A turn persists user + assistant messages, updates `last_message_at`, and (when triggered)
  refreshes the rolling summary.
- Conversation → Memory extraction proposes memories through the existing Memory Service with
  no bypass of consent/scoring/dedupe.
- New tests added; **full suite green**; existing Phase 1/1.5 tests unchanged.

---

## 2. Conversation System Architecture

```
        ┌───────────────────────────── API (FastAPI v1) ─────────────────────────────┐
        │  conversations.py · messages.py   (JWT-verified, tenant GUC set per request)│
        └───────────────────────────────────┬─────────────────────────────────────────┘
                                             ▼
                           ┌──────────────── Service layer ────────────────┐
                           │  conversation_service   (thread lifecycle)     │
                           │  message_service        (append turn, ordering)│
                           │  conversation_turn_service  (orchestrates turn)│ ◀── reuses chat pipeline
                           │  summary_service        (rolling/closing)      │
                           │  memory_extraction_service (chat → memory)     │ ◀── reuses Memory Engine
                           └───────┬───────────────┬───────────────┬────────┘
                                   ▼               ▼               ▼
                   ┌──────────── Repository layer (pure persistence) ───────────┐
                   │ conversation_repository · message_repository ·             │
                   │ conversation_summary_repository · conversation_search_repo │
                   └───────┬─────────────────────────────────────┬─────────────┘
                           ▼                                     ▼
                  ┌──────── New tables (RLS) ───────┐   ┌──── Reused (Phase 1/1.5) ────┐
                  │ conversations                    │   │ memories · memory_embeddings │
                  │ messages                         │   │ memory_versions · users      │
                  │ conversation_summaries           │   │ EmbeddingService · LLM gw    │
                  │ conversation_summary_embeddings  │   │ retrieval + context assembly │
                  └──────────────────────────────────┘   └──────────────────────────────┘
```

**The turn flow (Phase 2 core path):**

```
POST /conversations/{id}/messages  (or POST /conversations for a new thread)
  1. Auth → CurrentUser → tenant GUC set (existing).
  2. message_service.append(user message)         → messages row.
  3. conversation_turn_service:
       a. load recent messages for THIS thread     (message_repository, token-budgeted)
       b. load thread rolling summary              (conversation_summaries, latest)
       c. retrieve long-term memories              (memory_retrieval_service — REUSED)
       d. assemble_context(messages + summary + memories)  (context_assembly — extended)
       e. build_prompt + llm.generate              (prompt_builder + claude_gateway — REUSED)
  4. message_service.append(assistant message)     → messages row; bump last_message_at.
  5. (async/threshold) summary_service.refresh()   → new rolling summary + embedding.
  6. (async/threshold) memory_extraction_service   → propose memories (consent-gated, REUSED).
```

Steps 5–6 run **out of the request's critical path** — either via the existing worker
pattern (`embedding_worker`-style) or a post-commit task — so chat latency stays bounded.

---

## 3. Conversations Table Design

`conversations` — one row per thread. `TimestampMixin` + `UUIDPrimaryKeyMixin`.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | `gen_random_uuid()`. |
| `user_id` | uuid FK→users(id) `ON DELETE CASCADE`, NOT NULL | **tenant column for RLS**. |
| `title` | text NULL | auto-generated from first exchange; user-editable. NULL until generated. |
| `status` | enum(`active`,`archived`) NOT NULL default `active` | string-backed + CHECK. |
| `agent_context` | enum/text NULL | hub tag (`general`,`career`,`learning`,`research`,`builder`). **Forward seam** for Agent Framework routing; nullable now, defaults `general`. |
| `pinned` | bool NOT NULL default false | pin-to-top organization. |
| `last_message_at` | timestamptz NULL | sort key for recency groups; updated on each turn. |
| `message_count` | int NOT NULL default 0 | denormalized counter (cheap recency UI; maintained in service). |
| `deleted_at` | timestamptz NULL | soft delete (mirrors `memories`). |
| `created_at`/`updated_at` | timestamptz | from `TimestampMixin`. |

**Indexes** (tenant-first, mirroring the memories convention):
- `ix_conversations_user_id`
- `ix_conversations_user_id_status`
- `ix_conversations_user_id_last_message_at` (recency listing — the hot path)
- `ix_conversations_user_id_deleted_at`
- partial/where on `pinned` optional (low cardinality; defer).

**Constraints:** `status_valid` CHECK, `agent_context_valid` CHECK (if enum-ized).

> No `summary` *column* on `conversations` (unlike the Phase 0 sketch). Summaries get their
> own versioned table (§5) so we keep rolling history, support closing summaries, and embed
> them cleanly. The latest rolling summary is a 1-row lookup.

---

## 4. Messages Table Design

`messages` — append-only turns. `UUIDPrimaryKeyMixin` + **`CreatedAtMixin`** (immutable; no
`updated_at` — edits create new rows or are out of scope for Phase 2).

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `conversation_id` | uuid FK→conversations(id) `ON DELETE CASCADE`, NOT NULL | parent thread. |
| `user_id` | uuid FK→users(id) `ON DELETE CASCADE`, NOT NULL | **denormalized tenant column** — enables a *direct* column RLS policy (no subquery), matching the `memory_embeddings.user_id` decision in 0005. |
| `role` | enum(`user`,`assistant`,`system`,`tool`) NOT NULL | string-backed + CHECK. `tool` reserved for Agent Framework. |
| `content` | text NOT NULL | rendered message text. |
| `token_count` | int NULL | cached estimate (from `utils.tokens`) for budgeting. |
| `model` | text NULL | for assistant rows: which model produced it. |
| `input_tokens` / `output_tokens` | int NULL | assistant-row cost accounting (from `ChatResult`). |
| `metadata` | jsonb NULL | extensible: tool call ids, citations, agent id (forward seam). |
| `created_at` | timestamptz | ordering key. |

**Why denormalize `user_id` onto messages:** 0005 chose a direct `user_id` column on
`memory_embeddings` instead of a parent-subquery policy (see `memory_versions` which *does*
use a subquery). Messages are the highest-volume table and are read on every turn — a direct
column policy (`user_id = GUC`) is the cheaper, simpler, index-friendly choice. The service
sets `user_id` on insert from `CurrentUser`; a DB CHECK/trigger can assert it matches the
parent conversation's `user_id` (defense in depth; optional for Phase 2).

**Ordering:** by `(conversation_id, created_at, id)`. `id` (uuid) breaks ties
deterministically. Consider a per-conversation monotonic `seq int` if sub-millisecond
collisions matter — deferred unless tests show ordering flakiness.

**Indexes:**
- `ix_messages_conversation_id_created_at` (the load-recent-turns hot path)
- `ix_messages_user_id` (RLS predicate support)
- FTS: a GIN index on `to_tsvector('english', content)` for keyword search (§throughout).

---

## 5. Conversation Summaries

`conversation_summaries` — versioned rolling/closing summaries (append-only history).
`UUIDPrimaryKeyMixin` + `CreatedAtMixin`.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `conversation_id` | uuid FK→conversations(id) CASCADE, NOT NULL | |
| `user_id` | uuid FK→users(id) CASCADE, NOT NULL | direct RLS tenant column. |
| `summary_type` | enum(`rolling`,`closing`) NOT NULL | rolling = live compaction; closing = final distilled (on archive/idle). |
| `content` | text NOT NULL | the distilled summary. |
| `covers_through_message_id` | uuid FK→messages(id) NULL | watermark: summary reflects the thread up to this message. Lets the next refresh summarize only the delta. |
| `version_number` | int NOT NULL | 1-based per conversation (mirrors `memory_versions`). |
| `model` | text NULL | which (cheap-tier) model produced it. |
| `created_at` | timestamptz | |

**Embeddings:** `conversation_summary_embeddings` — separate table mirroring
`memory_embeddings` exactly (pgvector column, `user_id` for RLS, FK to summary).
**Reuse `EmbeddingService` + the `embedding_worker` sync pattern verbatim** — only the source
table differs. Semantic conversation search queries these vectors, not raw message vectors
(cheap + fast, per Phase 0 §4).

**Rolling-summary algorithm (service-owned):**
```
on threshold (e.g. N new messages since covers_through, or token pressure):
  base = latest rolling summary for thread (or empty)
  delta = messages after covers_through_message_id
  new_summary = llm.summarize(base + delta)          # cheap model tier
  insert conversation_summaries(rolling, version+1, covers_through=last msg id)
  enqueue embedding sync for the new summary
```
Thresholds live in `core/constants.py` (alongside `DEFAULT_CONTEXT_TOKEN_BUDGET`).

**Closing summary:** on archive or idle (a later scheduled job; Phase 2 fires it on explicit
archive), write a `closing` summary + embedding — the durable semantic handle for the thread.

---

## 6. Long-Term Memory Extraction Pipeline

The bridge from **conversations (raw material)** to **memory (distilled product)** — Phase 0
memory-system §3.1's "activity-derived" + "suggested" creation paths, realized.

```
conversation turn(s)
   └─ memory_extraction_service.extract(conversation_id, since=watermark)
        1. gather candidate window (recent messages + delta since last extraction)
        2. llm.extract_facts(window) → candidate facts
              {content, proposed_category, importance, confidence, source_message_id}
        3. FOR EACH candidate:
             → hand to the EXISTING Memory Service creation path:
                  classify → score → CONSENT CHECK → dedupe → embed → store
             → NOTHING bypasses consent, scoring, or dedupe.
        4. record provenance: link the created memory back to the conversation/message.
```

**Reuse, do not reinvent:** extraction produces *candidates*; the existing
`memory_service` creation pipeline (consent modes Explicit/Assisted/Autonomous, importance +
confidence scoring, supersession/dedupe, embedding) owns whether/how they persist. Sensitive
categories (health/finance/credentials) remain **never auto-saved**, exactly as today.

**Consent-mode behavior** (unchanged semantics, new trigger):
- *Explicit* — extraction proposes nothing automatically; only "remember this" commands flow.
- *Assisted (default)* — extraction surfaces proposals the user one-taps to accept.
- *Autonomous* — clearly-durable facts auto-saved + notified.

**Category:** extracted conversational facts default to their natural category
(`career`, `preference`, …); thread-level digests use the existing `conversation` category.

**Trigger cadence:** out-of-band (post-turn / threshold / on archive), never blocking the
reply. A watermark (`last_extracted_message_id`, stored on `conversations` or a small
sidecar) prevents re-processing.

---

## 7. Conversation → Memory Relationship

The linkage that makes provenance and "where did Gummy learn this?" answerable.

**Decision: a dedicated link table** `memory_sources` (append-only), rather than FK columns on
`memories` — because one memory may derive from multiple messages, and we must not modify the
frozen `memories` schema's semantics beyond an additive, optional link.

| `memory_sources` | Type | Notes |
| --- | --- | --- |
| `id` | uuid PK | |
| `user_id` | uuid FK→users CASCADE | RLS tenant column. |
| `memory_id` | uuid FK→memories(id) CASCADE | the distilled product. |
| `conversation_id` | uuid FK→conversations(id) `ON DELETE SET NULL` | source thread. |
| `message_id` | uuid FK→messages(id) `ON DELETE SET NULL` | source turn (nullable). |
| `source_kind` | enum(`conversation`) NOT NULL | extensible: later `document`, `activity`. |
| `created_at` | timestamptz | |

**Why `SET NULL` on conversation/message delete:** a memory is durable and user-owned; it
should survive deletion of its source chat (the user may delete a thread but keep the fact).
The link simply loses its back-pointer. This realizes "conversations are raw material; memory
is the distilled product" — they have **independent lifecycles**.

**Cascade-clarity (Phase 0 memory §3.3):** deleting a conversation can *offer* to delete
derived memories (a service-level UX decision), but the DB default is to preserve memory.

This table is also the **shared seam for future agents**: any agent that creates a memory
records its provenance here (`source_kind` grows), so the Memory Center can always show "who/
what created this" across the whole agent workforce.

---

## 8. Context Retrieval Flow (per turn)

Extends `context_assembly_service` from "memories only" to a **layered context pack**, while
keeping the function pure and token-budgeted.

```
context budget = DEFAULT_CONTEXT_TOKEN_BUDGET, allocated in priority order:
  1. System / personality prompt              (existing prompt_builder; reserved)
  2. Recent THIS-thread messages              (newest-first until sub-budget)   ← NEW
  3. Thread rolling summary (older context)   (1 row; latest rolling)            ← NEW
  4. Long-term memories (cross-thread)        (memory_retrieval_service — REUSED)
  5. [Phase 3+] document chunks               (seam only)
  6. [Agent Framework] tool/agent outputs     (seam only)
```

**Implementation:** introduce a richer `ContextPackage` (or a wrapping `TurnContext`) that
carries `messages`, `summary`, and `memories` segments each with their own token accounting,
preserving the existing dedupe/budget logic. `chat_service.chat()` is refactored into
`conversation_turn_service` that:
- still calls `memory_retrieval_service.retrieve_memories(...)` unchanged,
- additionally loads recent messages + latest rolling summary via the new repos,
- composes the layered pack, then `build_prompt` + `llm.generate` as today.

**Budget policy:** recent-messages and memories each get a sub-budget so neither starves the
other; the rolling summary is the compaction valve that keeps long threads cheap. Constants in
`core/constants.py`.

The current stateless `chat_service` either (a) becomes a thin shim delegating to the new
turn service, or (b) is retired once the API moves to conversation endpoints — decided at
implementation review to avoid breaking existing `test_chat_*` tests prematurely.

---

## 9. RLS Strategy for New Tables

**Principle: identical pattern to 0005 — direct `user_id` column policy, fail-closed.** Every
new table carries a `user_id` tenant column so we use the *simple direct policy*, avoiding
parent-subquery policies on hot tables.

For each of `conversations`, `messages`, `conversation_summaries`,
`conversation_summary_embeddings`, `memory_sources`:

```sql
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
CREATE POLICY <t>_tenant_isolation ON <t>
  FOR ALL
  USING      (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid)
  WITH CHECK (user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);
```

- **Fail-closed:** unset GUC ⇒ NULL ⇒ zero rows. No tenant, no data.
- **`gummy_app` role:** runs without RLS bypass (already the runtime role). Owners/
  `service_role` bypass for migrations/ops only.
- **No parent-subquery policies** for the high-volume `messages` table — the denormalized
  `user_id` (§4) is precisely to enable the cheap direct policy.
- **Cross-table integrity:** WITH CHECK on insert guarantees a tenant cannot insert a message/
  summary under a foreign `user_id`. An optional trigger asserting
  `messages.user_id = conversations.user_id` adds defense in depth (consider; not required).
- **Verification:** extend the integration test (`test_rls_postgres.py` style) to prove
  cross-tenant reads/writes are blocked on every new table under `gummy_app`. **This is an
  exit-criteria gate.**

---

## 10. API Design (FastAPI `v1`)

New routers under `app/api/v1/`, registered in `router.py`. All JWT-protected via existing
`deps` (`get_current_user` → tenant GUC). Schemas in `app/schemas/conversation.py`,
`message.py`.

**Conversations**
| Method · Path | Purpose |
| --- | --- |
| `POST /v1/conversations` | Create a thread (optionally with a first message → triggers a turn). |
| `GET /v1/conversations` | List threads (recency-grouped; filters: `status`, `agent_context`, `pinned`; pagination). |
| `GET /v1/conversations/{id}` | Thread metadata + latest summary. |
| `PATCH /v1/conversations/{id}` | Rename, pin/unpin, archive (`status`). |
| `DELETE /v1/conversations/{id}` | Soft delete (`deleted_at`); optional cascade-offer for memories. |
| `GET /v1/conversations/{id}/messages` | Paginated message history (ascending, cursor by `created_at,id`). |

**Turns / messages**
| Method · Path | Purpose |
| --- | --- |
| `POST /v1/conversations/{id}/messages` | **The turn endpoint** — append user message, run the pipeline, persist + return assistant message. |

**Search**
| Method · Path | Purpose |
| --- | --- |
| `GET /v1/conversations/search?q=&mode=keyword\|semantic\|hybrid` | Keyword (messages FTS) + semantic (summary embeddings); deep-link to thread/message. |

**Conventions:** envelope/pagination shapes mirror existing `memories` API; errors via
`core/exceptions`; request/response models are Pydantic schemas — no ORM leakage. (Streaming
SSE variant of the turn endpoint is a documented future extension, not Phase 2.)

---

## 11. Service Layer Design

Module-level async functions (matching the codebase), each owning a unit of work and
committing once at the boundary; repositories only flush.

- **`conversation_service`** — create/list/get/rename/pin/archive/soft-delete; maintains
  `last_message_at`, `message_count`; owns title auto-generation (cheap LLM call on first
  exchange).
- **`message_service`** — append a message (sets `user_id`, `role`, `token_count`); load
  token-budgeted recent window for a thread; enforce append-only.
- **`conversation_turn_service`** — orchestrates the turn (§2/§8). Reuses
  `memory_retrieval_service`, `context_assembly_service`, `prompt_builder`, `claude_gateway`.
  This is the refactor target of today's `chat_service`.
- **`summary_service`** — rolling/closing summary generation + version bump + embedding
  enqueue (§5). Cheap model tier.
- **`memory_extraction_service`** — candidate extraction → hand-off to existing
  `memory_service` creation path; writes `memory_sources` provenance (§6/§7).
- **`conversation_search_service`** — keyword (FTS) + semantic (summary-embedding similarity)
  + hybrid merge; maps to deep-links.

**Cross-cutting:** all writes are tenant-scoped via the GUC (RLS enforces; services still pass
`user_id` explicitly for clarity + index use, as the memory layer does). Summary +
extraction are dispatched **post-commit / via worker**, never inline-blocking the reply.

---

## 12. Repository Layer Design

Pure persistence, module functions, `flush`-not-commit, no business logic (mirrors
`memory_repository`). New modules:

- **`conversation_repository`** — `create`, `get` (tenant-scoped, exclude soft-deleted),
  `list` (filters + recency order + count), `update_fields`, `touch_last_message`,
  `soft_delete`.
- **`message_repository`** — `append`, `list_for_conversation` (asc, paginated),
  `recent_window` (newest-first up to a token/row budget), `count_for_conversation`.
- **`conversation_summary_repository`** — `add_version`, `latest_rolling`,
  `next_version_number` (mirrors `memory_repository.next_version_number`), `list_for_conversation`.
- **`conversation_summary_embedding_repository`** — mirror of `memory_embedding_repository`
  (insert/replace vector, fetch by similarity), reusing pgvector helpers.
- **`conversation_search_repository`** — FTS query over `messages`, vector query over summary
  embeddings.
- **`memory_source_repository`** — `link`, `list_for_memory`, `list_for_conversation`.

All queries are tenant-scoped in SQL **and** protected by RLS (belt + suspenders, matching the
existing layer).

---

## 13. Migration Roadmap

Linear chain continuing from `0005_enable_rls`. Each migration: forward + working downgrade,
deterministic constraint names, RLS enabled **in the same migration that creates the table**
(so no window exists where a tenant table is unprotected).

| Rev | Migration | Contents |
| --- | --- | --- |
| `0006` | `add_conversations` | `conversations` table + indexes + CHECKs; ENABLE RLS + `conversations_tenant_isolation`. |
| `0007` | `add_messages` | `messages` table (denormalized `user_id`) + indexes + FTS GIN; ENABLE RLS + policy. |
| `0008` | `add_conversation_summaries` | `conversation_summaries` + `conversation_summary_embeddings` (pgvector) + indexes; ENABLE RLS + policies on both. |
| `0009` | `add_memory_sources` | `memory_sources` link table (FKs, `SET NULL` on source delete); ENABLE RLS + policy. |
| `0010` *(opt)* | `add_extraction_watermark` | `conversations.last_extracted_message_id` (or sidecar) if not folded into 0006. |

Pgvector extension is already present (used by `memory_embeddings`); no new extension needed.
Migrations verified against the live DB via the Supabase MCP only after local review.

---

## 14. Testing Strategy

Mirror the existing test taxonomy (unit → repo → service → api → RLS integration). Keep the
Phase 1/1.5 suite untouched and green.

- **Models** (`test_conversation_models.py`) — columns, defaults, CHECK constraints, enums.
- **Repositories** — CRUD, ordering (`conversation_id, created_at, id`), pagination,
  soft-delete exclusion, summary version increment, provenance links. (SQLite-compatible
  where the existing repo tests are; pgvector/FTS paths covered in the Postgres tests.)
- **Services** —
  - `conversation_service`: lifecycle, counters, title generation (fake LLM).
  - `message_service`: append + recent-window budgeting.
  - `conversation_turn_service`: full turn with **fake LLM + fake embeddings**, asserting both
    messages persisted, `last_message_at` bumped, layered context assembled.
  - `summary_service`: rolling refresh on threshold, watermark advance, embedding enqueue.
  - `memory_extraction_service`: candidates routed through the real memory creation path;
    consent modes honored; sensitive categories never auto-saved; `memory_sources` written.
- **API** (`test_conversation_api.py`, `test_message_api.py`) — auth required, tenant scoping,
  CRUD, turn endpoint shape, search modes, pagination/cursors.
- **RLS integration** (extend `test_rls_postgres.py`) — under `gummy_app`, cross-tenant reads/
  writes on **every** new table return zero / are rejected; unset GUC ⇒ no rows. **Gate.**
- **Regression** — existing `test_chat_*` still pass (shim) or are migrated deliberately.

Reuse `fake_provider` (LLM) and `fake_provider` (embeddings) so service/turn tests are
deterministic and offline.

---

## 15. Risks and Tradeoffs

| Risk / decision | Tradeoff | Mitigation |
| --- | --- | --- |
| **Denormalized `user_id` on messages/summaries** | Slight write redundancy; must stay consistent with parent. | Simpler/cheaper RLS on the hottest table; set from `CurrentUser`; optional consistency trigger. Consistent with 0005's `memory_embeddings` choice. |
| **Async summary + extraction** | Eventual consistency: a fact may not be a memory the instant it's said. | Acceptable per Phase 0 (memory is "distilled product"); watermark prevents loss; can force-run on archive. |
| **LLM cost of summaries/extraction** | Extra model calls per thread. | Cheap model tier; threshold-triggered (not every turn); rolling delta-only summarization. |
| **Refactoring `chat_service`** | Risk to passing `test_chat_*`. | Keep a shim delegating to `conversation_turn_service`; migrate tests deliberately, not in a rush. |
| **Summary quality drives memory quality** | Bad summaries → bad recall/extraction. | Keep raw messages as source of truth; summaries are derived + versioned (re-derivable); extraction reads messages, not only summaries. |
| **Message volume growth** | `messages` becomes the largest table. | Tenant-first indexes; pagination by cursor; FTS GIN; partitioning is a future option (schema is partition-ready by `created_at`). |
| **Context budget tuning** | Mis-allocation starves memories or recent turns. | Sub-budgets in constants; covered by turn-service tests; tunable without schema change. |
| **Ordering ties** | Same-millisecond `created_at`. | `id` tiebreak now; add per-thread `seq` only if tests show flakiness. |

---

## 16. Future Compatibility

Phase 2 is designed so later phases **add**, never **rewrite**. Concrete seams:

**Agent Framework (Phase 3+)**
- `conversations.agent_context` + `messages.role='tool'` + `messages.metadata.agent_id`
  already model multi-agent threads.
- `conversation_turn_service` is the natural insertion point for the **Master Orchestrator**:
  today it calls one pipeline; tomorrow it calls the Orchestrator, which fans out to agents.
  The persistence/summary/extraction layers are agent-agnostic and unchanged.
- The typed turn result already carries model/token/cost — extend to
  `{output, proposed_actions, proposed_memories, citations, cost}` from agent-framework §5.

**Workflow Learning**
- `memory_sources` (provenance) + versioned summaries give the audit trail a learning loop
  needs ("which conversations produced which durable knowledge / outcomes").
- `metadata` jsonb on messages can record workflow/step ids without schema change.

**GSD (Get-Stuff-Done) Execution Layer**
- The `tool` role + `metadata` (tool call ids, results) model tool execution turns in-thread.
- Action proposals surface as assistant messages with `metadata.proposed_actions`; the future
  Action Agent / permission engine consumes them. No new message plumbing needed.

**Multi-Agent Workforce vision**
- **One shared memory, one provenance table:** every future agent writes memories through the
  same `memory_service` and records provenance in `memory_sources` (just a new `source_kind`).
  The Memory Center stays the single, complete, user-owned view across the entire workforce.
- Stateless services + tenant-scoped RLS mean agents scale horizontally with zero tenancy
  rework; the conversation thread is the shared substrate agents collaborate on.

> The throughline matches agent-framework §10: **stable contract + central policy + shared
> memory**. Phase 2 delivers the shared *conversation + memory substrate* those agents stand
> on, without committing to any orchestration implementation yet.

---

## 17. Architecture Diagram (Phase 2 end-state)

```
┌──────────────────────────────────── REQUEST ────────────────────────────────────┐
│ JWT (Supabase HS256) ─► get_current_user ─► CurrentUser ─► tenant ContextVar     │
│                                   │  (after_begin hook sets app.current_user_id)  │
└───────────────────────────────────┼───────────────────────────────────────────────┘
                                     ▼
        ┌──────────────────────── API v1 (FastAPI) ───────────────────────┐
        │ /conversations  /conversations/{id}/messages  /…/search          │
        └───────────────┬──────────────────────────────────────────────────┘
                        ▼
        ┌──────────────────────── SERVICES ────────────────────────────────┐
        │ conversation │ message │ conversation_turn │ summary │ extraction │
        └───────┬───────────────────┬──────────────────┬───────────┬────────┘
                │                   │                  │           │
   ┌────────────┘        ┌──────────┘         ┌────────┘     ┌─────┘ (post-commit / worker)
   ▼                     ▼                    ▼              ▼
REPOSITORIES        REUSED Phase 1/1.5    REUSED retrieval  REUSED Memory Engine
conversation        EmbeddingService      memory_retrieval  memory_service (consent,
message             claude_gateway        + context_assembly  scoring, dedupe, embed)
summary(+embed)     prompt_builder                │              │
search · sources                                  │              │ writes
   │                                              │              ▼
   ▼                                              │         memories · memory_embeddings
┌──────────────── POSTGRES (RLS, gummy_app) ──────┴──────────────────────────────┐
│ conversations · messages · conversation_summaries · …_embeddings ·             │
│ memory_sources        ║   memories · memory_embeddings · memory_versions · users│
│  (NEW, RLS fail-closed)║   (FROZEN Phase 1/1.5)                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
        every table: user_id = NULLIF(current_setting('app.current_user_id',true),'')::uuid
```

---

## 18. Engineering Milestones / Tasks

**M1 — Schema & RLS foundation**
- [ ] Models: `Conversation`, `Message`, `ConversationSummary`, `ConversationSummaryEmbedding`, `MemorySource` + enums (`ConversationStatus`, `MessageRole`, `SummaryType`, `AgentContext`, `SourceKind`).
- [ ] Migrations `0006–0009` (+`0010` opt): tables, indexes, FTS GIN, CHECKs, RLS in-migration.
- [ ] RLS integration tests (extend `test_rls_postgres.py`) — **gate**.

**M2 — Repositories**
- [ ] `conversation` / `message` / `conversation_summary` / `summary_embedding` / `search` / `memory_source` repositories + unit tests.

**M3 — Conversation lifecycle services + API**
- [ ] `conversation_service` + `message_service`; `/conversations` CRUD + `/messages` history; schemas; API tests.

**M4 — The turn (chat persistence)**
- [ ] `conversation_turn_service` (refactor of `chat_service`); layered `context_assembly`; `/conversations/{id}/messages` turn endpoint; shim old chat path; service + API tests.

**M5 — Summaries**
- [ ] `summary_service` (rolling + closing) + embedding sync via worker pattern; threshold constants; tests.

**M6 — Conversation → Memory extraction**
- [ ] `memory_extraction_service` routing candidates through existing `memory_service`; `memory_sources` provenance; consent-mode + sensitive-category tests.

**M7 — Search**
- [ ] `conversation_search_service` (keyword + semantic + hybrid); `/conversations/search`; tests.

**M8 — Hardening & seal**
- [ ] Full-suite green; advisors/lint; docs update; tag `phase2-complete`.

---

## 19. Recommended Implementation Order

```
M1 (schema+RLS)  →  M2 (repos)  →  M3 (lifecycle+API)  →  M4 (the turn)
                                          │
                                          ├─►  M5 (summaries)  ─┐
                                          │                     ├─►  M7 (search)  ─►  M8 (seal)
                                          └─►  M6 (extraction) ─┘
```

Rationale: persistence before intelligence. Get threads + messages durable and RLS-proven
(M1–M3) so the system is correct and safe, then make the turn stateful (M4). Summaries (M5)
and extraction (M6) are independent enrichments on top of stored messages and can proceed in
parallel; search (M7) depends on summaries' embeddings. Each milestone keeps the suite green
and is independently reviewable.

---

## 20. Estimated Scope & Complexity

| Milestone | New files (≈) | Complexity | Risk |
| --- | --- | --- | --- |
| M1 Schema + RLS | 5 models + 4–5 migrations + tests | Medium | RLS correctness (gate) |
| M2 Repositories | 6 repos + tests | Low–Med | Low (established pattern) |
| M3 Lifecycle + API | 2 services + 2 routers + schemas | Medium | API surface |
| M4 The turn | 1 service (refactor) + endpoint | **Med–High** | Refactor + budget tuning |
| M5 Summaries | 1 service + worker glue | Medium | LLM cost/quality |
| M6 Extraction | 1 service + provenance | **Med–High** | Consent correctness |
| M7 Search | 1 service + endpoint | Medium | FTS + vector merge |
| M8 Seal | docs + tag | Low | — |

**Overall: Medium-High.** The two genuinely hard parts are (a) **RLS correctness on the new
high-volume tables** (mitigated by copying 0005's proven direct-column pattern + a gating
integration test) and (b) **wiring extraction into the existing consent pipeline without
bypassing it** (mitigated by routing strictly through `memory_service`). Everything else
follows established Phase 1/1.5 patterns. No frozen code is modified; the only refactor
(`chat_service` → `conversation_turn_service`) is shielded by a shim.

---

## 21. Resolved Decisions (v1) — was "Open Questions"

These were the open questions; all are now **resolved for GUMMY OS v1**. Each records the
decision, the rejected alternatives, and the rationale.

| # | Question | **v1 Decision** | Rejected | Rationale |
| --- | --- | --- | --- | --- |
| 1 | Title generation timing | **Async backfill** — placeholder = truncated first user message; real title generated post-commit (cheap tier), row updated. | Sync-on-first-turn; pure heuristic | First turn is the worst place to spend latency (a core Phase 2 goal); reuses the shared post-commit dispatcher (Q2/Q3); matches ChatGPT/Claude/Gemini behavior. |
| 2 | Summary trigger | **Token-pressure primary + message-count safety cap** (whichever fires first). | Pure count; pure token | The summary exists to control the token budget, so token-pressure is the metric that maps to the goal; `estimate_tokens` already exists; count cap guards the many-tiny-messages case. Thresholds in `core/constants.py`. |
| 3 | Extraction cadence | **Batched on the summary trigger** (same watermark/delta window), **consent-gated**; explicit "remember this" takes an **immediate** path; no auto-extraction in *Explicit* mode. | Every turn; archive-only | One shared trigger/window/watermark = minimal machinery; bounds LLM cost without bad lag; explicit commands stay instant; honors the existing consent contract unchanged. |
| 4 | `chat_service` fate | **Shim in M4, retire as a named M8 task.** | Migrate immediately; keep forever | Low risk while the turn path stabilizes (protects the green baseline); clean single-path end state before sealing; explicit retirement prevents permanent debt. |
| 5 | `messages.user_id` consistency trigger | **No trigger** — rely on tenant-scoped service + RLS `WITH CHECK`; document the invariant. | DB trigger now | The mismatch window is already closed (conversation-level RLS read + message-level `WITH CHECK`); a trigger on the hottest table guards nothing new. Matches 0005's direct-column posture. Add only if a non-service write path appears. |
| 6 | Plan location | **`docs/`** (beside `PHASE1_5_PLAN.md`). Confirmed. | repo root | Convention + discoverability with the other phase plans, ROADMAP, VISION. |

### 21.1 Consolidation that falls out of Q1–Q3

Resolving title backfill, rolling summary, and memory extraction *together* collapses three
separately-sketched async jobs into **one shared post-commit enrichment pass** over a single
watermark/delta window:

```
turn committed ──► enrichment dispatcher  (post-commit, OUT of the request critical path)
                     ├─ title backfill    (first exchange only)             [Q1]
                     ├─ rolling summary    (token-pressure / N-message cap)  [Q2]
                     └─ memory extraction  (same window, consent-gated)      [Q3]
  explicit "remember this" ──► immediate path → memory_service  (bypasses the batch, any mode)
```

One trigger, one delta window, one watermark advance — not three independent cadences. This
reshapes the milestones: the **enrichment dispatcher seam lands in M4**; title/summary/
extraction become its **consumers** in M5/M6.

---

## 22. Finalized Phase 2 Architecture Recommendation

Unchanged from §2–§17 except for the consolidation above. The committed v1 shape:

1. **Persistence first.** `conversations` + `messages` (denormalized `user_id`) +
   versioned `conversation_summaries` (+ embeddings) + `memory_sources` provenance — every
   table RLS fail-closed under `gummy_app`, created with its policy in the same migration.
2. **The turn** = `conversation_turn_service` (refactor of `chat_service`, shimmed): persist
   user msg → layered token-budgeted context (recent messages + rolling summary + reused
   hybrid memory retrieval) → `prompt_builder` + `claude_gateway` → persist assistant msg →
   bump `last_message_at` → **enqueue one enrichment pass**.
3. **One post-commit enrichment dispatcher** drives title backfill, token-pressure-triggered
   rolling summaries (+ embedding sync via the existing worker pattern), and batched
   consent-gated memory extraction — all off a single watermark. Explicit memory commands
   bypass it via the immediate path.
4. **Memory stays the distilled product.** Extraction only produces *candidates*; the
   **existing `memory_service`** owns consent/scoring/dedupe/embedding. Sensitive categories
   never auto-save. Provenance recorded in `memory_sources` (memories outlive deleted chats).
5. **Search** = messages FTS (keyword) + summary-embedding similarity (semantic) + hybrid.
6. **Zero changes to frozen seams** — auth, tenant GUC, RLS pattern, retrieval, embeddings,
   LLM gateway, and the memory engine are all reused as-is.

## 23. Finalized Implementation Order

```
M1 schema+RLS ─► M2 repos ─► M3 lifecycle+API ─► M4 the turn + enrichment-dispatcher seam
                                                        │
                                                        ├─►  M5 enrichment consumers
                                                        │      (title backfill + rolling
                                                        │       summaries + embeddings)
                                                        │            │
                                                        └─►  M6 extraction consumer ──┐
                                                               (consent-gated, M5     ├─► M7 search ─► M8 seal
                                                                dispatcher reused)     │   (needs summary
                                                                                       │    embeddings)
```

**Sequencing rationale.** Persistence and RLS correctness come first (M1–M3) — get threads
durable and tenant-isolation *proven* before adding intelligence. M4 makes the turn stateful
**and** introduces the post-commit enrichment dispatcher with no-op consumers (so the seam
exists and is tested empty). M5 attaches the title + summary consumers; M6 attaches the
extraction consumer (reusing M5's dispatcher) and writes provenance. M7 (search) depends on
M5's summary embeddings. M8 retires the `chat_service` shim, greens the full suite, and tags
`phase2-complete`. Every milestone keeps the suite green and is independently reviewable.

**Net change from the original order:** title generation moves out of M3 into M5 (it is now an
enrichment consumer, not a lifecycle concern); M4 additionally owns the dispatcher seam; M8
gains the explicit shim-retirement task.

---

_No code is to be written until this plan is reviewed and approved. All §21 questions are
resolved. On approval, begin at M1 (schema + RLS), continuing the migration chain from
`0005_enable_rls`._
