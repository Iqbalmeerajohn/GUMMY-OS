# GUMMY OS — Phase 2 Progress

Living log of Phase 2 (Conversation System) implementation. Plan of record:
[PHASE2_PLAN.md](PHASE2_PLAN.md). Updated continuously, milestone by milestone.

Baseline at start: tag `phase1.5-complete`, migration head `0005_enable_rls`,
test suite `106 passed, 1 skipped`.

---

## Status board

| Milestone | Scope | Status |
| --- | --- | --- |
| **M1** | Schema + RLS foundation (5 tables, migrations 0006–0009) | ✅ **Complete & gate-verified on live Postgres** |
| **M2** | Repositories (pure persistence) | ✅ **Complete** |
| **M3** | Conversation lifecycle services + API | ✅ **Complete** |
| **M4** | The turn + enrichment-dispatcher seam | ✅ **Complete** |
| **M5** | Enrichment consumers (title + summaries + embeddings) | ✅ **Complete** |
| **M6** | Conversation → Memory extraction | ✅ **Complete** |
| M7 | Conversation search | ⏳ Not started |
| M8 | Hardening & seal | ⏳ Not started |

---

## M1 — Schema & RLS foundation ✅

**Goal:** persist conversations durably and tenant-isolated before adding any
intelligence. All five Phase 2 tables created with RLS enabled in the same
migration that creates each table (no unprotected window).

### Delivered

**Enums** ([app/models/enums.py](../backend/app/models/enums.py), additive only):
`ConversationStatus`, `AgentContext`, `MessageRole`, `SummaryType`, `SourceKind`.

**Models** (new files):
- [conversation.py](../backend/app/models/conversation.py) — `conversations`
- [message.py](../backend/app/models/message.py) — `messages` (denormalized `user_id`; `metadata` JSONB mapped via `extra_metadata`)
- [conversation_summary.py](../backend/app/models/conversation_summary.py) — `conversation_summaries` (versioned, watermark FK `SET NULL`)
- [conversation_summary_embedding.py](../backend/app/models/conversation_summary_embedding.py) — `conversation_summary_embeddings` (pgvector, SQLite-JSON variant)
- [memory_source.py](../backend/app/models/memory_source.py) — `memory_sources` (provenance; FK-only links keep Phase 1 `Memory` untouched)
- [models/__init__.py](../backend/app/models/__init__.py) — registration (additive only).

**Migrations** (linear `0005 → 0009`):
- `0006_add_conversations` — table, 4 indexes, CHECKs, RLS policy.
- `0007_add_messages` — table, composite + tenant index, **GIN FTS index** over `content`, RLS policy.
- `0008_add_conversation_summaries` — summaries + summary embeddings (**HNSW cosine index**), RLS on both.
- `0009_add_memory_sources` — provenance table, `SET NULL` source FKs, RLS policy.

Every policy uses the identical fail-closed GUC predicate as 0005:
`user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid`.

**Tests**:
- [test_conversation_models.py](../backend/tests/test_conversation_models.py) — 15 tests: table/column/index/constraint registration, enum values, relationship wiring, the `extra_metadata`→`metadata` mapping, a 63-char identifier-limit guard, and a "Phase 1 untouched" sanity check.
- [test_rls_postgres.py](../backend/tests/test_rls_postgres.py) — extended with `test_conversation_tables_isolation_under_rls` (the M1 RLS gate; skip-gated on `RUN_RLS_PG_TESTS` + `RLS_TEST_DSN`).

### Verification performed

| Check | Result |
| --- | --- |
| Models import + `Base.metadata.create_all` on SQLite | ✅ all 9 tables build |
| `alembic heads` | ✅ single head `0009_add_memory_sources` |
| `alembic history` | ✅ linear `0001…0009`, no branches |
| `alembic upgrade 0005:head --sql` (offline render) | ✅ all DDL emits: tables, RLS policies, FTS GIN, HNSW, `SET NULL` FKs, CHECKs, JSONB |
| `ruff check app/ tests/` | ✅ all checks passed |
| `mypy` (new models + migrations) | ✅ no issues in 15 files |
| `pytest` (full suite) | ✅ **121 passed, 2 skipped** (was 106/1; +15 model tests, +1 skip-gated RLS test) |

### Issues found & resolved during M1
1. **Over-long FK identifier.** One auto-generated FK name on
   `conversation_summary_embeddings` exceeded Postgres's 63-char limit (SQLite did
   not enforce it). Fixed with an explicit short name
   `fk_conv_summary_embeddings_summary_id` in **both** model and migration; added a
   metadata test guarding all Phase 2 identifiers ≤ 63.
2. **Missing `gummy_app` grants on new tables (found during the live gate run).**
   The one-time `ALTER DEFAULT PRIVILEGES` did not propagate to owner-created
   migration tables (role-context mismatch), so `gummy_app` had **no** CRUD on the
   five new tables — the RLS test would have failed with "permission denied" rather
   than testing isolation. Fixed by a **conditional grant in each migration**
   (`GRANT … TO gummy_app` guarded by `IF EXISTS (… pg_roles …)`), so the table's
   access policy (RLS *and* grants) travels with the table and fresh environments
   still apply cleanly. Verified `has_table_privilege` = true on all five tables.

### M1 gate — CLOSED ✅ (live Postgres, `gummy_app` non-bypass role)
Verified against the live Supabase project (head advanced `0005 → 0009`):

| Gate check | Result |
| --- | --- |
| `alembic upgrade head` on live Postgres | ✅ 0006–0009 applied |
| `alembic downgrade 0005` → `upgrade head` cycle | ✅ downgrade path verified, re-applied clean |
| RLS enabled + 1 GUC policy per table (USING + WITH CHECK) | ✅ all 5 tables |
| `gummy_app` CRUD grants on all 5 tables | ✅ after grant fix |
| **Conversation isolation** | ✅ Bob sees 0 of Alice's |
| **Message isolation** | ✅ Bob sees 0 |
| **Summary isolation** (+ summary embeddings) | ✅ Bob sees 0 |
| **memory_sources isolation** | ✅ Bob sees 0 |
| **Fail-closed** (unset GUC) on all 5 tables | ✅ 0 rows |
| **WITH CHECK** rejection (forged cross-tenant insert) | ✅ on `conversations` and `memory_sources` |
| `pytest tests/test_rls_postgres.py` as `gummy_app` | ✅ **2 passed** |
| Supabase security advisors on new tables | ✅ none flagged (no `rls_enabled_no_policy`) |
| Test self-cleanup | ✅ all 5 tables back to 0 rows |

The RLS test (`test_conversation_tables_isolation_under_rls`) now inserts a full FK
chain (conversation → message → summary → summary-embedding, plus memory →
memory_source) and asserts isolation + fail-closed across **all five** tables, with
WITH CHECK on two. It remains skip-gated in the fast suite (`RUN_RLS_PG_TESTS=1` +
`RLS_TEST_DSN`), runnable any time against a `gummy_app` DSN.

Pre-existing advisor warnings (pgvector in `public` from 0003; `alembic_version`
RLS-no-policy; legacy `rls_auto_enable` function) are **out of M1 scope** — not
introduced by Phase 2.

### Notes on "Phase 1/1.5 untouched"
- No existing model columns, migrations, services, or tests were modified.
- Two Phase 1 files received **additive-only** changes required to register new
  models: `enums.py` (new enum classes appended) and `models/__init__.py` (new
  imports/exports). No existing definitions were altered; `test_phase1_models_untouched`
  asserts the frozen relationships are intact.

---

## M2 — Repositories ✅

**Goal:** the pure-persistence data-access layer for the Phase 2 tables — module
functions, build/run queries, `flush()` (never commit), no business logic. Mirrors
`memory_repository`.

### Delivered (new files)
- [conversation_repository.py](../backend/app/repositories/conversation_repository.py) — create, get (tenant-scoped, soft-delete-aware), list (filters: status/agent_context/pinned; recency order: pinned → `last_message_at` → created_at; + total), update_fields, touch_last_message, soft_delete.
- [message_repository.py](../backend/app/repositories/message_repository.py) — append (assigns `seq`), list (paginated, ordered by seq + total), recent_messages (cap + chronological), count, next_seq.
- [conversation_summary_repository.py](../backend/app/repositories/conversation_summary_repository.py) — next_version_number, add_summary, latest_summary (overall / by type), list_summaries.
- [conversation_summary_embedding_repository.py](../backend/app/repositories/conversation_summary_embedding_repository.py) — get/create/update/list (mirror of `memory_embedding_repository`).
- [memory_source_repository.py](../backend/app/repositories/memory_source_repository.py) — link_source, list_for_memory, list_for_conversation.

**Tests:** [test_conversation_repository.py](../backend/tests/test_conversation_repository.py) — 16 tests across all five repos: CRUD, tenant scoping, pagination + totals, recency/pinned ordering, filters, soft-delete exclusion, message seq ordering + recent-window cap, summary version increment + latest-by-type, embedding CRUD, provenance link + lookups.

### Schema addition found during M2 — `messages.seq` (migration 0010)
Two message-ordering tests failed initially: `created_at` is **fixed per Postgres
transaction** (and second-resolution on SQLite), so messages appended together
collide and the random uuid PK is no reliable tiebreak — non-deterministic order.
This is exactly the risk flagged in PHASE2_PLAN.md §4. Fix: added a monotonic
per-conversation **`seq`** ordinal (BigInteger, assigned at append) with a
`UNIQUE(conversation_id, seq)` constraint; all message ordering now keys on `seq`.

- Migration **0010_add_message_seq** (head advances `0009 → 0010`). Column added
  NOT NULL directly — `messages` carries no rows until the app writes (post-M3), so
  no backfill. Applied to live Postgres; down/up cycle verified.

### Scope note — `conversation_search_repository` deferred to M7
The plan lists a search repository under M2 *and* M7. Its FTS + pgvector ranking is
Postgres-only and not unit-testable on the SQLite suite, so it is built and verified
in **M7 (Search)** alongside the search service (same pattern as the existing
`search_repository`). M2 delivers the five SQLite-testable repositories.

### Verification
| Check | Result |
| --- | --- |
| `ruff check app/ tests/` | ✅ all passed |
| `mypy` (repositories + models) | ✅ no issues, 21 files |
| `alembic heads` | ✅ single head `0010_add_message_seq` |
| `pytest` (full suite, SQLite) | ✅ **137 passed, 2 skipped** (was 121/2; +16 repo tests) |
| 0010 applied to live Postgres + down/up cycle | ✅ |
| RLS gate re-run under `gummy_app` (post-schema-change) | ✅ **2 passed** |

---

## M3 — Conversation lifecycle services + API ✅

**Goal:** make conversations usable end-to-end — create/list/get/rename·pin·archive/
soft-delete a thread, and read its message history — without any turn, enrichment,
summary, extraction, retrieval, or search logic (those are M4–M7). Narrow lifecycle
scope only.

### Delivered (new files)
- **Services** (new `app/services/conversation/` package — domain-separated from memory):
  - [conversation_service.py](../backend/app/services/conversation/conversation_service.py) — create, get (404), list (filters + pagination), update (rename/pin/archive/re-tag; empty-update → 400), soft-delete. Owns the transaction boundary; `ConversationNotFoundError` / `EmptyUpdateError`.
  - [message_service.py](../backend/app/services/conversation/message_service.py) — `list_messages` (history), ownership-checked (resolves the conversation first → 404 for unknown/foreign threads).
- **Schemas**: [conversation.py](../backend/app/schemas/conversation.py) (Create/Update/Response/ListResponse, title validation) · [message.py](../backend/app/schemas/message.py) (read-only `MessageResponse`; ORM `extra_metadata` exposed to clients as `metadata` via `validation_alias`).
- **API** ([conversations.py](../backend/app/api/v1/conversations.py), registered in `router.py`):
  - `POST /api/v1/conversations` · `GET /api/v1/conversations` (status/agent_context/pinned filters) · `GET /{id}` · `PATCH /{id}` · `DELETE /{id}` (204) · `GET /{id}/messages` (history).
- **Constant**: `CONVERSATION_TITLE_MAX_LENGTH = 200`.

### Scope discipline (explicitly NOT in M3)
No turn endpoint / message creation, no enrichment dispatcher, no summaries, no
memory extraction, no retrieval orchestration, no search. Repository ↔ service ↔
API separation preserved (HTTP thin, services own the unit of work, repos persist).
The stateless `chat_service` is untouched (its shim/retirement is M4/M8).

### Verification
| Check | Result |
| --- | --- |
| `ruff check app/ tests/` | ✅ all passed |
| `mypy app/` | ✅ no issues, 85 files |
| `pytest` (full suite, SQLite) | ✅ **156 passed, 2 skipped** (was 137/2; +19 M3 tests) |
| App-level tenant isolation (API test: other tenant → list 0 / get 404) | ✅ |
| `metadata` alias serialization (`extra_metadata` → `metadata`) | ✅ |
| Live RLS gate re-run under `gummy_app` (no regression; M3 has no migrations) | ✅ 2 passed |
| Live head unchanged at `0010` | ✅ |

Tests added: `test_conversation_service.py` (10), `test_conversation_api.py` (9).

---

_Next: M4 — the turn (`conversation_turn_service`, refactor of `chat_service` via a
shim) + the post-commit enrichment-dispatcher seam (no-op consumers); the
`POST /conversations/{id}/messages` turn endpoint._

---

## M4 — The turn + enrichment-dispatcher seam ✅

**Goal:** make a conversation turn stateful — persist the user message and the
assistant reply, replay recent thread history as working memory, update the
thread's recency/counter, and introduce the **post-commit enrichment dispatcher
seam** (consumers are no-op stubs). Reuses the existing memory pipeline unchanged.

### Delivered (new files)
- [conversation_turn_service.py](../backend/app/services/conversation/conversation_turn_service.py):
  - `generate_grounded_reply(...)` — the **stateless** reply core (retrieve →
    assemble → prompt → LLM), now shared by the turn and the chat shim; takes
    optional `history`.
  - `run_turn(...)` — the **persistent** turn: 404-checks ownership, loads recent
    prior messages as history, persists user + assistant messages, bumps
    `last_message_at` + `message_count`, commits, then dispatches enrichment.
    Returns `TurnResult`.
- [enrichment.py](../backend/app/services/conversation/enrichment.py) — the
  **dispatcher seam**: `EnrichmentJob`, three ordered **no-op consumer stubs**
  (`_backfill_title` → M5, `_refresh_rolling_summary` → M5, `_extract_memories` →
  M6), and `dispatch(...)`. One shared post-commit trigger (PHASE2_PLAN.md §21.1).

### Changed files
- [chat_service.py](../backend/app/services/memory/chat_service.py) — refactored into
  a **compatibility shim**: same `chat()` signature + `ChatResult`, now delegating to
  `generate_grounded_reply`. Slated for retirement in M8. (`test_chat_*` unchanged
  and green.)
- [prompt_builder.py](../backend/app/services/memory/prompt_builder.py) — `build_prompt`
  gains optional `history` (prepended before the query); default `None` keeps the
  legacy single-message prompt identical.
- [schemas/message.py](../backend/app/schemas/message.py) — `TurnRequest` + `TurnResponse`.
- [api/v1/conversations.py](../backend/app/api/v1/conversations.py) — `POST
  /conversations/{id}/messages` turn endpoint (wires embeddings + LLM + settings).
- [constants.py](../backend/app/core/constants.py) — `DEFAULT_TURN_HISTORY_MESSAGES = 20`.

### Scope discipline (explicitly NOT in M4)
Enrichment consumers stay **no-op stubs** — no title generation, summaries,
extraction, or search. The rolling-summary *context layer* is also deferred (no
summaries exist yet); M4's turn context = recent thread history + long-term
memories. Repository ↔ service ↔ API separation preserved. No new migration.

### Verification
| Check | Result |
| --- | --- |
| `ruff check app/ tests/` | ✅ all passed |
| `mypy app/` | ✅ no issues, 87 files |
| `pytest` (full suite, SQLite) | ✅ **170 passed, 2 skipped** (was 156/2; +14 M4 tests) |
| `test_chat_*` still green under the shim (no behavior change) | ✅ |
| App-level turn tenant isolation (foreign tenant → 404) | ✅ |
| Live RLS gate re-run under `gummy_app` (no regression; M4 adds no migration) | ✅ 2 passed |
| Live head unchanged at `0010` | ✅ |

Tests added: `test_conversation_turn_service.py` (8: persistence, lifecycle,
history replay, memory grounding, 404, enrichment dispatched, consumers-are-no-ops,
shim-is-stateless) and `test_turn_api.py` (6: 201 + persistence, counter bump,
empty-message 422, unknown-conv 404, auth required, tenant isolation).

### Interruption/resume note
This milestone was finished after a session-limit interruption: M4 implementation
+ the service test were already on disk (uncommitted); resuming completed a fragile
datetime assertion fix (SQLite returns naive datetimes for `timezone=True` columns —
test-only coercion; product code unchanged), added the turn API test file, ran the
full verification, and updated this doc.

---

_Next: M5 — enrichment consumers (title backfill + rolling summaries + summary
embeddings); replaces the no-op stubs and extends the turn context with the rolling
summary layer._

---

## M5 — Enrichment consumers (title + rolling summaries + embeddings) ✅

**Goal:** turn the M4 no-op enrichment seam into real, background consumers — title
backfill and rolling summaries (+ their embeddings) — and feed the rolling summary
back into the turn's context. The **extraction consumer stays a no-op stub** (M6).

### Architecture: the enrichment moved onto a background worker
The consumers need a DB session + LLM + embeddings, and must stay off the turn's
latency path. So enrichment now mirrors the existing `embedding_worker`:
- [enrichment_worker.py](../backend/app/workers/enrichment_worker.py) — a singleton
  drained by one asyncio task; configured at lifespan with sessionmaker + LLM +
  embedding service. Each consumer runs in **its own session/transaction** so a
  failure is isolated and never crashes the worker. `enqueue` is a no-op when idle
  (so unit/API tests are unaffected and the turn stays instant).
- The turn now calls `enrichment_worker.enqueue(...)` post-commit (was
  `enrichment.dispatch(...)`). Wired into `main.py` lifespan alongside the embedding
  worker.

### Delivered
- **Title consumer** — [conversation_service.backfill_title](../backend/app/services/conversation/conversation_service.py):
  generates a 3–6 word title from the first user message via the LLM; idempotent
  (no-op if already titled / no messages / conversation gone); flush-only.
- **Rolling summary consumer** — [summary_service.py](../backend/app/services/conversation/summary_service.py):
  computes the unsummarized **delta** (messages after the previous summary's
  watermark), fires on **token-pressure OR a message-count cap** (PHASE2_PLAN.md §21
  Q2), summarizes *previous summary + delta* into a new versioned rolling summary,
  and **embeds** it (pgvector via the existing embedding provider). Flush-only.
- **Extraction consumer** — remains a **NO-OP stub** ([enrichment.py](../backend/app/services/conversation/enrichment.py) `extract_memories`).
- **Context-assembly summary layer** — [prompt_builder.build_prompt](../backend/app/services/memory/prompt_builder.py)
  gains an optional `summary` (rendered as a `<conversation_summary>` block); the
  turn loads the latest rolling summary and injects it. Backward compatible (default
  `None` → legacy prompt; chat shim passes none).
- **Repo helpers** — `message_repository.get_message` + `messages_after` (delta
  query by `seq`).
- **Constants** — `SUMMARY_TRIGGER_TOKEN_THRESHOLD=500`, `SUMMARY_TRIGGER_MESSAGE_COUNT=6`,
  `SUMMARY_MAX_DELTA_MESSAGES=100`.

### Scope discipline (explicitly NOT in M5)
No memory extraction (stub only), no search. Repo ↔ service ↔ worker separation
preserved (services flush; the worker owns the commit). No new migration. The
`chat_service` shim is untouched (its stateless path passes no summary).

### Verification
| Check | Result |
| --- | --- |
| `ruff check app/ tests/` | ✅ all passed |
| `mypy app/` | ✅ no issues, 89 files |
| `pytest` (full suite, SQLite) | ✅ **185 passed, 2 skipped** (was 170/2; +15 M5 tests) |
| Worker end-to-end (title + summary persisted; failing consumer isolated; idle no-op) | ✅ |
| Rolling summary injected into turn prompt; chat shim still stateless | ✅ |
| Live RLS gate re-run under `gummy_app` (no regression; M5 adds no migration) | ✅ 2 passed |
| Live head unchanged at `0010` | ✅ |

Tests added: `test_summary_service.py` (5), `test_enrichment_worker.py` (3), title
backfill in `test_conversation_service.py` (3), summary/history in
`test_prompt_builder.py` (4), rolling-summary injection in
`test_conversation_turn_service.py` (1). M4 enrichment tests updated for the worker
switch (enqueue spy; extraction-still-no-op).

---

_Next: M6 — conversation→memory extraction (consent-gated, routed through the
existing Memory Engine) + `memory_sources` provenance; replaces the `extract_memories`
stub._

---

## M6 — Conversation → Memory extraction ✅

**Goal:** turn conversations into durable long-term memory — distil facts from new
messages and persist them **exclusively through the existing Memory Engine**,
consent-gated, with provenance, without reprocessing.

### Delivered
- [memory_extraction_service.py](../backend/app/services/conversation/memory_extraction_service.py) — the extraction pipeline:
  1. **Consent gate** (`ConsentMode`): only `autonomous` auto-saves; `explicit` and
     `assisted` persist nothing automatically (assisted's proposal surface is future
     work). Resolved from `settings.memory_consent_mode` (default **`assisted`** —
     safe: nothing auto-saved until a tenant opts in).
  2. **Delta + threshold**: works the unsummarized delta after the per-conversation
     watermark; fires on the same token/count cadence as summaries (plan Q3).
  3. **LLM extraction** → JSON candidates (code-fence tolerant; invalid
     JSON/category dropped; sensitive-category guard wired but currently empty).
  4. **Reuse, don't duplicate**: every candidate goes through
     `memory_service.create_memory` (scoring defaults, versioning, embedding sync) —
     no memory logic reimplemented.
  5. **Provenance**: a `memory_sources` link (memory → conversation) per created
     memory.
- **Watermark** — `conversations.last_extracted_seq` (migration **0011**) +
  `conversation_repository.set_extraction_watermark`. Advanced *before* persistence
  so the worker's commit/rollback gives clean semantics: on LLM failure the whole
  unit of work rolls back (window retried, not silently skipped); on success the
  window is marked processed (no re-extraction / duplicates).
- **Consumer wired** — `enrichment.extract_memories` now calls the service (was the
  M4/M5 no-op stub). Title + summary consumers **unchanged**.
- `ConsentMode` enum; `memory_consent_mode` setting; `EXTRACTION_MAX_MEMORIES`.

### Scope discipline (explicitly honored)
Memory Engine reused **exclusively** (no duplicated memory logic); all extracted
memories routed through `memory_service`; consent-gated; provenance created &
verified; title/summary consumers untouched; **no search**; repo/service/worker
separation preserved.

### Migration fix found during the live apply
The first revision id (`0011_add_conversation_extraction_watermark`, 42 chars)
exceeded Alembic's `alembic_version.version_num` **VARCHAR(32)** on Postgres — the
`ADD COLUMN` ran but recording the version failed; transactional DDL rolled it back
cleanly (no partial state). Shortened to **`0011_extraction_watermark`**; SQLite
tests don't enforce this length, which is why it only surfaced on the live apply.

### Verification
| Check | Result |
| --- | --- |
| `ruff` / `mypy` | ✅ clean (91 files) |
| `pytest` (full suite, SQLite) | ✅ **194 passed, 2 skipped** (was 185/2; +9 M6 tests) |
| Consent gate (autonomous saves; explicit/assisted save nothing) | ✅ |
| Routed through Memory Engine (default scores) + provenance link created | ✅ |
| Watermark prevents re-extraction (no duplicates) | ✅ |
| Worker e2e in autonomous mode (memory + provenance persisted) | ✅ |
| 0011 applied to live Postgres + down/up cycle; column `bigint`, `gummy_app` UPDATE inherited | ✅ |
| Live RLS gate re-run under `gummy_app` | ✅ 2 passed |
| Live head | ✅ `0011_extraction_watermark` |

Tests added: `test_memory_extraction_service.py` (8: autonomous-with-provenance,
explicit/assisted gates, below-threshold, watermark-prevents-reextraction,
invalid-category skip, unparseable output, code-fenced JSON) + autonomous worker
e2e in `test_enrichment_worker.py` (1); model column assertion updated.

### Known limitation (noted, not in scope)
Cross-window semantic duplicates (the *same* fact restated in a later delta) aren't
de-duplicated — true dedup is a Memory-Engine concern, deliberately not added here.
The watermark eliminates same-window reprocessing.

---

_Next: M7 — conversation search (`conversation_search_repository` FTS over messages +
pgvector over summary embeddings + search service/API)._
