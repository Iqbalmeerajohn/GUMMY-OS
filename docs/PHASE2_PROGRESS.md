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
| M2 | Repositories | ⏳ Not started |
| M3 | Conversation lifecycle services + API | ⏳ Not started |
| M4 | The turn + enrichment-dispatcher seam | ⏳ Not started |
| M5 | Enrichment consumers (title + summaries + embeddings) | ⏳ Not started |
| M6 | Conversation → Memory extraction | ⏳ Not started |
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

_Next: M2 — repositories (pure persistence, module functions, flush-not-commit)._
