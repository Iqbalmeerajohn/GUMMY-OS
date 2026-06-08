# GUMMY OS — Phase 2 Architecture (as implemented)

The **Conversation System** as actually built across milestones M1–M8 (tag
`phase2-complete`). This describes the shipped code, not the original
[PHASE2_PLAN.md](PHASE2_PLAN.md); where the implementation diverged from the plan it
is called out. Migration head: `0011_extraction_watermark`.

---

## 1. System overview

Phase 2 adds a persistent, memory-aware conversation layer on top of the Phase 1
**Memory Engine** and Phase 1.5 **JWT + RLS** foundation — both reused unchanged.

```
                            ┌──────────────────────────────────────────┐
   Client ── Bearer JWT ──▶ │  FastAPI (app.main:app)                   │
                            │   /api/v1/conversations/*   /api/v1/memories/* │
                            └───────────────┬──────────────────────────┘
                                            │ get_current_user → tenant ContextVar
                                            ▼
              ┌──────────────────────────  Services  ──────────────────────────┐
              │ conversation · message · conversation_turn · summary ·          │
              │ memory_extraction · conversation_search   (app/services/        │
              │ conversation/)            ── reuse ──▶ memory_service,           │
              │                                        memory_retrieval,         │
              │                                        context_assembly,         │
              │                                        prompt_builder,           │
              │                                        embedding_service         │
              └───────────────┬───────────────────────────────────┬────────────┘
                              │ (request path)                     │ (post-commit)
                              ▼                                     ▼
                    Repositories (flush-only)            Background workers
                    conversation/message/summary/        embedding_worker (reused)
                    summary_embedding/memory_source/      enrichment_worker (new)
                    conversation_search
                              │                                     │
                              ▼                                     ▼
              ┌──────────── PostgreSQL (Supabase) — role: gummy_app (NOBYPASSRLS) ┐
              │ conversations · messages · conversation_summaries ·               │
              │ conversation_summary_embeddings · memory_sources    (Phase 2)     │
              │ memories · memory_embeddings · memory_versions · users (Phase 1)  │
              │ pgvector (HNSW) · GIN full-text · Row-Level Security (fail-closed) │
              └───────────────────────────────────────────────────────────────────┘
```

**Layering rule (enforced throughout):** HTTP is thin → services own business logic
and the unit of work (commit) → repositories are pure persistence (`flush`, never
commit) → workers run enrichment off the request path.

---

## 2. Request flow

Every request to a versioned endpoint:

```
1. HTTP request with `Authorization: Bearer <jwt>` (or, in dev, ?user_id=…).
2. get_current_user (api/deps.py):
     verify HS256 JWT → CurrentUser → set_current_user_id(sub) [ContextVar]
     → upsert local users row.
3. DbSession dependency opens an AsyncSession; the SQLAlchemy `after_begin` hook
   reads the ContextVar and runs:
       SELECT set_config('app.current_user_id', <uuid>, false)
   on the transaction — this is what RLS keys off.
4. The endpoint delegates to a service (no logic in the route).
5. The service calls repositories (flush) and commits once at the boundary.
6. Response is shaped by a Pydantic schema (no ORM leakage).
7. get_db clears the tenant ContextVar so it never leaks across requests on a
   pooled connection.
```

Reference: [deps.py](../backend/app/api/deps.py), [tenant_context.py](../backend/app/core/tenant_context.py),
[database/session.py](../backend/app/database/session.py).

---

## 3. Authentication flow

```
Authorization: Bearer <jwt>
        │
        ▼
verify_access_token(token, settings)        # HS256, supabase_jwt_secret, aud check
        │  claims.sub (uuid), claims.email
        ▼
set_current_user_id(claims.sub)             # publish tenant BEFORE any DB work
        │
        ▼
user_repository.upsert_user(sub, email)     # get-or-create local users row
        │
        ▼
CurrentUser(id, email)  ──▶ CurrentUserId (uuid) injected into every endpoint
```

- **Dev/legacy fallback:** when `auth_dev_bypass` is on and no token is present, a
  `?user_id=` query param (or `auth_dev_user_id`) is accepted — this is how the
  hermetic test suite drives tenancy on SQLite.
- **No new auth surface in Phase 2** — conversation endpoints use the exact same
  `CurrentUserId` dependency as memories.
- A startup guard (`assert_auth_safe`) refuses to boot if the dev bypass is enabled
  in production.

---

## 4. RLS flow (tenant isolation)

Identical, fail-closed pattern on every Phase 1 **and** Phase 2 table.

```
per transaction:  app.current_user_id = '<tenant-uuid>'   (set by after_begin hook)

policy on each table (USING + WITH CHECK):
    user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
```

- **Fail-closed:** if the GUC is unset, `current_setting(..., true)` is NULL →
  `NULLIF(...)::uuid` is NULL → **zero rows** (and inserts rejected).
- **Direct-column policies everywhere.** Every Phase 2 table carries `user_id`
  (denormalized on `messages`, `conversation_summaries`,
  `conversation_summary_embeddings`, `memory_sources`) so the policy is a cheap
  column compare — no parent subqueries, even on the high-volume `messages` table.
- **Non-bypass role.** The app connects as `gummy_app` (`NOSUPERUSER NOBYPASSRLS`);
  the owner/`service_role` connection is used only for migrations.
- **Grants travel with the table.** Each Phase 2 migration issues a conditional
  `GRANT … TO gummy_app` (guarded by `IF EXISTS (… pg_roles …)`) — added after M1's
  live run revealed `ALTER DEFAULT PRIVILEGES` didn't cover owner-created tables.
- **Verified live** under `gummy_app` (`tests/test_rls_postgres.py`, gated): per-table
  isolation, fail-closed, WITH CHECK rejection, and search isolation.

Reference: migrations [0006](../backend/app/database/migrations/versions/0006_add_conversations.py)–[0009](../backend/app/database/migrations/versions/0009_add_memory_sources.py).

---

## 5. Conversation flow (the turn)

The single memory-aware chat entrypoint (the legacy stateless `/chat` route was
retired in M8). Endpoint: `POST /api/v1/conversations/{id}/messages`.

```
run_turn(session, user_id, conversation_id, message, embeddings, llm, …):

  1. conversation_service.get_conversation         → 404 if not the tenant's
  2. message_repository.recent_messages            → prior turns (working memory)
  3. conversation_summary_repository.latest_summary(ROLLING) → rolling summary text
  4. message_repository.append_message(role=user)  → persists, assigns seq
  5. generate_grounded_reply(...)  ── stateless core, reused: ──────────────────┐
        a. memory_retrieval_service.retrieve_memories  (hybrid, pgvector)        │
        b. context_assembly_service.assemble_context   (token-budgeted, dedupe)  │
        c. prompt_builder.build_prompt(memories, history, summary)               │
        d. llm.generate(system, messages)                                        │
  6. message_repository.append_message(role=assistant, model, tokens)            │
  7. message_repository.count_messages → conversation_repository.touch_last_message
  8. session.commit()                              → atomic: both msgs + lifecycle
  9. enrichment_worker.enqueue(conversation_id, user_id)   ── post-commit, async ─┘
 10. return TurnResult (reply, ids, token counts, message_count)
```

**Context layering** assembled into the prompt (per turn):
`system/personality + recent thread messages (history) + rolling summary
(<conversation_summary>) + long-term memories (<memory>) + current query`.

**Ordering guarantee:** messages sort by a monotonic per-conversation `seq`
(BigInteger, `UNIQUE(conversation_id, seq)`), not `created_at` — because `created_at`
is fixed per Postgres transaction and second-resolution on SQLite, so it can't break
ties for messages appended together.

Lifecycle endpoints (M3): `POST /conversations`, `GET /conversations`
(status/agent_context/pinned filters, recency order), `GET /{id}`, `PATCH /{id}`
(rename/pin/archive/re-tag), `DELETE /{id}` (soft delete), `GET /{id}/messages`.

Reference: [conversation_turn_service.py](../backend/app/services/conversation/conversation_turn_service.py),
[conversations.py](../backend/app/api/v1/conversations.py).

---

## 6. Memory flow (read + write)

Phase 2 **reads from** and **writes to** the Phase 1 Memory Engine without modifying
it.

**Read (per turn):**
```
retrieve_memories (memory_retrieval_service)
  → search_repository.search_similar_memories  (pgvector cosine, Postgres-only)
  → hybrid re-rank (semantic + importance + recency + confidence)
  → context_assembly_service  (token budget, dedupe)
  → prompt_builder <memory> block
```

**Write (from a conversation, autonomous consent only):**
```
memory_extraction_service.extract_and_store
  → memory_service.create_memory(MemoryCreate)   # THE Memory Engine — scoring
                                                  # defaults, version 1, embedding
                                                  # enqueue. No logic duplicated.
  → memory_source_repository.link_source          # provenance: memory → conversation
```

**Provenance** (`memory_sources`) links a memory back to the conversation it came
from. `ON DELETE SET NULL` on the conversation/message FKs and `ON DELETE CASCADE`
on the memory FK mean a durable, user-owned memory **survives** deletion of its
source chat (the link just loses its back-pointer).

---

## 7. Extraction flow (conversation → memory)

Runs as a background enrichment consumer, consent-gated, watermarked.

```
extract_and_store(session, user_id, conversation_id, llm, consent_mode):

  consent gate:   resolve mode (settings.memory_consent_mode, default "assisted")
                  └─ EXPLICIT  → return []        (no automatic extraction)
                  └─ ASSISTED  → return []        (proposals = future work; safe)
                  └─ AUTONOMOUS→ proceed

  delta:          messages_after(seq > conversations.last_extracted_seq)
  trigger:        fire when delta tokens ≥ THRESHOLD OR delta count ≥ CAP
                  (same cadence as summaries; below threshold → return [])

  watermark FIRST: set last_extracted_seq = delta[-1].seq   (flush)
                   └─ on LLM failure the whole unit of work rolls back → retried;
                      on success the window is marked processed → no re-extraction.

  llm.generate(transcript) → JSON candidates [{content, category}]
                   (code-fence tolerant; invalid JSON/category dropped;
                    sensitive-category guard wired but currently empty)

  per candidate (≤ EXTRACTION_MAX_MEMORIES):
       memory_service.create_memory(...)          # reuse Memory Engine
       memory_source_repository.link_source(...)  # provenance
```

The watermark eliminates same-window reprocessing (and thus duplicate memories);
cross-window semantic dedup is left to the Memory Engine (not added).

Reference: [memory_extraction_service.py](../backend/app/services/conversation/memory_extraction_service.py).

---

## 8. Search flow

Endpoint: `GET /api/v1/conversations/search?q=&mode=keyword|semantic|hybrid&limit=`
(registered **before** `/{conversation_id}` so "search" isn't parsed as an id).

```
conversation_search_service.search(mode):

  keyword  (KEYWORD|HYBRID):  conversation_search_repository.keyword_search
        to_tsvector('english', messages.content) @@ plainto_tsquery('english', q)
        ranked by ts_rank   (GIN index ix_messages_content_fts, from 0007)
        → rows (conversation_id, message_id, rank)

  semantic (SEMANTIC|HYBRID): summary_semantic_search
        embed_query(q) → pgvector cosine (<=>) over conversation_summary_embeddings
        (HNSW index, from 0008)
        → rows (conversation_id, summary_id, distance)

  fold to conversation level:
        keyword → best normalized rank + match_message_id per conversation
        semantic → best similarity (1 - distance) per conversation

  rank:   KEYWORD → norm_rank · SEMANTIC → similarity ·
          HYBRID  → 0.5·norm_rank + 0.5·similarity     (weights in constants)

  hydrate: re-fetch each hit via conv_repo.get_conversation (tenant-scoped,
           non-deleted) — defense in depth + skips since-deleted threads.
  → ranked ConversationSearchHit[] (deep-linkable: match_message_id)
```

Both searches are tenant-scoped in SQL **and** under RLS; the repo queries are
PostgreSQL-only (FTS + pgvector) with pure `build_*_statement` helpers
(compile-tested) — live isolation proven under `gummy_app`.

Reference: [conversation_search_repository.py](../backend/app/repositories/conversation_search_repository.py),
[conversation_search_service.py](../backend/app/services/conversation/conversation_search_service.py).

---

## 9. Database schema diagram

```
 users (Phase 1)
   id (uuid, pk)
     ▲ user_id (every table below; RLS tenant column)
     │
 ┌───┴─────────────────────────────────────────────────────────────────────────┐
 │ conversations                       (0006; 0011 adds last_extracted_seq) │
 │   id pk · user_id fk→users CASCADE                                            │
 │   title? · status{active,archived} · agent_context{general,career,…}          │
 │   pinned · last_message_at? · message_count · last_extracted_seq · deleted_at?│
 │   created_at · updated_at                                                     │
 └───┬───────────────────────────────────────────────────────────────────────────┘
     │ 1                                                          1 │
     │ N (CASCADE)                                          N (CASCADE)
 ┌───▼──────────────────────────────┐          ┌──────────────────▼──────────────┐
 │ messages              (0007/0010) │          │ conversation_summaries    (0008)│
 │   id pk · conversation_id fk      │          │   id pk · conversation_id fk    │
 │   user_id fk · seq (uniq c_id,seq)│◀───SET   │   user_id fk                    │
 │   role{user,assistant,system,tool}│   NULL   │   summary_type{rolling,closing} │
 │   content · token_count? · model? │   covers_│   content · version_number      │
 │   input/output_tokens? · metadata │   through│   (uniq c_id, version) · model? │
 │   created_at                      │   _message_id?                            │
 │   GIN(to_tsvector(content)) [FTS] │          │   created_at                    │
 └───────────────────────────────────┘          └──────────────────┬──────────────┘
                                                              1 │ N (CASCADE)
                                                  ┌──────────────▼──────────────────┐
                                                  │ conversation_summary_embeddings  │
                                                  │   id pk · summary_id fk          │
                                                  │   user_id fk · embedding_model   │
                                                  │   embedding_dimension·content_hash│
                                                  │   embedding_vector vector(384)   │
                                                  │   HNSW(vector_cosine_ops)        │
                                                  │   (uniq summary_id, model)       │
                                                  └──────────────────────────────────┘
 ┌───────────────────────────────────────────────────────────────────────────────┐
 │ memory_sources                                                          (0009) │
 │   id pk · user_id fk→users CASCADE                                             │
 │   memory_id   fk→memories(id)       CASCADE   (Phase 1 table — link only)      │
 │   conversation_id fk→conversations  SET NULL                                   │
 │   message_id      fk→messages       SET NULL                                   │
 │   source_kind{conversation} · created_at                                       │
 └───────────────────────────────────────────────────────────────────────────────┘

 Every table: RLS ENABLED, policy `user_id = GUC` (fail-closed), gummy_app granted.
 Enums are string-backed (native_enum=False) with explicit CHECK constraints.
```

Migrations: `0006` conversations · `0007` messages (+FTS) · `0008` summaries +
embeddings · `0009` memory_sources · `0010` message `seq` · `0011` extraction
watermark.

---

## 10. Service layer diagram

`app/services/conversation/` (Phase 2 domain) — module functions; services own the
transaction (except enrichment services which flush so the worker commits).

```
conversation_service        create · get · list · update · delete · backfill_title(M5)
message_service             list_messages (ownership-checked history)
conversation_turn_service   generate_grounded_reply (stateless core) · run_turn
summary_service             maybe_refresh_rolling_summary (+ embedding)
memory_extraction_service   extract_and_store (consent-gated)
conversation_search_service search (keyword · semantic · hybrid)
enrichment                  EnrichmentJob · backfill_title · refresh_rolling_summary
                            · extract_memories · ENRICHMENT_CONSUMERS

   reuses (app/services/memory/, unchanged) ──────────────────────────────────
   memory_service · memory_retrieval_service · context_assembly_service ·
   prompt_builder ;  app/services/embeddings/embedding_service ;
   app/services/llm (claude_gateway / fake)
```

Dependency direction (no cycles): `conversation_turn_service → memory.* +
enrichment_worker`; `enrichment → conversation_service, summary_service,
memory_extraction_service`; `memory_extraction_service → memory_service`. Nothing in
the memory domain imports the conversation domain.

---

## 11. Repository layer diagram

`app/repositories/` — pure persistence, `flush` never `commit`, no business logic.

```
conversation_repository              create · get · list(filters+recency) · update
                                     · touch_last_message · set_extraction_watermark
                                     · soft_delete
message_repository                   append (assigns seq) · next_seq · list ·
                                     recent_messages · get_message · messages_after
                                     · count_messages
conversation_summary_repository      next_version_number · add_summary ·
                                     latest_summary(by type) · list_summaries
conversation_summary_embedding_repo  get · create · update · list   (mirror of
                                     memory_embedding_repository)
memory_source_repository             link_source · list_for_memory ·
                                     list_for_conversation
conversation_search_repository       build_keyword_statement · build_summary_
                                     semantic_statement · keyword_search ·
                                     summary_semantic_search   (PostgreSQL-only)
```

Every query is tenant-scoped in SQL **and** protected by RLS (belt + suspenders,
matching the Phase 1 repositories).

---

## 12. Worker architecture

Two in-process asyncio workers, both configured + started in the `main.py` lifespan
(only when a database is configured) and stopped on shutdown. `enqueue` is a **no-op
when idle**, so the request path never blocks and the hermetic test suite (no
running worker) is unaffected.

```
embedding_worker (Phase 1, reused)
   queue of (memory_id, user_id) → embed memory in its own session, retries.
   Enqueued by memory_service.create_memory — so extracted memories get embedded.

enrichment_worker (Phase 2, M5)                         enqueued by run_turn (post-commit)
   queue of EnrichmentJob(conversation_id, user_id)
   _process(job): for consumer in ENRICHMENT_CONSUMERS:
        async with sessionmaker() as session:           # OWN session per consumer
            await consumer(session, job, llm, embedding_service)
            await session.commit()                       # worker owns the commit
        except Exception: log + continue                 # isolated, best-effort
   consumers (ordered): backfill_title → refresh_rolling_summary → extract_memories
```

**Why a worker, not synchronous post-commit:** title/summary/extraction make LLM
calls; running them in-request would add seconds to the turn. The worker keeps the
turn instant and isolates failures (one bad consumer never blocks the others or the
reply).

Reference: [enrichment_worker.py](../backend/app/workers/enrichment_worker.py),
[embedding_worker.py](../backend/app/workers/embedding_worker.py).

---

## 13. Key engineering decisions

1. **Denormalized `user_id` on every Phase 2 table** → cheap direct-column RLS even
   on `messages` (the highest-volume table); no parent-subquery policies.
2. **One shared post-commit enrichment trigger** (the plan's §21.1 consolidation):
   title, summary, and extraction are consumers of a single `enrichment_worker`
   pass per turn — one queue, isolated sessions — instead of three cadences.
3. **Monotonic `seq` for message ordering** (migration 0010) after tests showed
   `created_at` collides within a Postgres transaction. Deterministic, insertion-
   faithful, `UNIQUE(conversation_id, seq)`.
4. **Extraction reuses the Memory Engine exclusively** — candidates are routed
   through `memory_service.create_memory`; no scoring/versioning/embedding logic is
   reimplemented. Provenance is the only new write.
5. **Consent-gated, watermark-first extraction** — `autonomous` auto-saves;
   `assisted`/`explicit` persist nothing; the watermark is advanced inside the same
   unit of work so failures retry and successes never duplicate.
6. **Rolling summaries are versioned + embedded** — each refresh is a new
   `conversation_summaries` row (never an overwrite) with its own embedding, so
   semantic conversation search is over compact summaries, not raw messages.
7. **Grants in the migration** — the table's full access policy (RLS *and* grants)
   travels with the table; surfaced and fixed during M1's live apply.
8. **Short Alembic revision ids** — `alembic_version.version_num` is VARCHAR(32);
   `0011`'s id was shortened after a long id failed to record on Postgres.
9. **Background workers over external infra** — in-process asyncio queues (no
   Redis/Celery), consistent with Phase 1's `embedding_worker`.
10. **Single chat entrypoint** — M8 retired the stateless `/chat` shim;
    `generate_grounded_reply` survives as the internal reply core of `run_turn`.

---

## 14. Known limitations

- **Assisted consent has no proposal surface.** `assisted` (the default) persists
  nothing automatically; only `autonomous` auto-saves. A proposals store + frontend
  is future work — the current default is deliberately safe (memory is earned).
- **No cheap-tier model routing.** Title/summary/extraction use the LLM provider's
  default model; routing to `claude_model_fast` is a deferred cost optimization.
- **No cross-window semantic memory dedup.** The extraction watermark prevents
  same-window reprocessing, but the *same fact* restated in a later window can
  create a second memory — true dedup is a Memory-Engine concern, not added here.
- **Rolling only, no closing summaries.** `SummaryType.CLOSING` exists in the schema
  but nothing triggers it on archive/idle yet; only rolling summaries are produced.
- **Search re-fetches conversations per hit** (`get_conversation` in a loop) — fine
  for `limit ≤ 50`; a batched `IN (...)` fetch is a later optimization.
- **In-process workers** — enrichment/embedding run in the app process; horizontal
  scale-out would need a shared queue (the consumer contract is already isolated).
- **Token-budgeted history is count-capped** (`DEFAULT_TURN_HISTORY_MESSAGES`), not
  yet token-trimmed per the plan's sub-budget idea.

---

## 15. Future extension points

The phase deliberately leaves seams for later phases:

- **Agent Framework / Orchestrator (next phase).** `conversation_turn_service.run_turn`
  is the insertion point: today it calls one pipeline; tomorrow it can call a Master
  Orchestrator that fans out to agents. `messages.role = 'tool'` + `messages.metadata`
  (JSONB) already model tool/agent turns; `conversations.agent_context` tags threads
  by hub. Persistence, summaries, and extraction are agent-agnostic.
- **Shared provenance bus.** `memory_sources.source_kind` is an enum with one value
  (`conversation`); adding `document` / `activity` lets any future agent record where
  a memory came from, keeping the Memory Center a complete, user-owned view.
- **New enrichment consumers** plug into `ENRICHMENT_CONSUMERS` (e.g. closing
  summaries, entity tagging) with zero turn-path changes.
- **Pluggable LLM/embeddings** — the `LLMProvider` and `EmbeddingProvider` protocols
  already abstract Claude/HF; OpenAI/Gemini slot in behind the factories.
- **Consent modes** — `ConsentMode` + `memory_consent_mode` is the gate a per-user
  settings store and the Assisted proposal flow will build on.
- **Streaming** — the turn persistence model is stream-ready; an SSE variant of the
  turn endpoint can be added without schema changes.

---

_Related: [PHASE2_PLAN.md](PHASE2_PLAN.md) (design of record) ·
[PHASE2_PROGRESS.md](PHASE2_PROGRESS.md) (milestone log) ·
[../architecture/conversation-system.md](../architecture/conversation-system.md) ·
[../architecture/memory-system.md](../architecture/memory-system.md)._
