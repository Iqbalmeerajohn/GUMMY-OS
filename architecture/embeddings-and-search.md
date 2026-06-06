# GUMMY OS — Embeddings & Semantic Search

> How memories become vectors and how semantic recall is computed. This is the
> retrieval substrate the Memory Service and agents build on.

> **Scope:** Phase 1, Day 4 — embeddings + pgvector + semantic search **only**. No
> RAG, context assembly, agent orchestration, or Claude reasoning (those are later).
> **Status:** Implemented. Realizes [memory-system.md §6](memory-system.md) and
> [tech-stack.md §4](tech-stack.md).

---

## 1. Embedding Model — `all-MiniLM-L6-v2`

**Decision:** `sentence-transformers/all-MiniLM-L6-v2` (Hugging Face), 384 dimensions.

| Why | Detail |
| --- | --- |
| **Lightweight** | ~80 MB, ~22M params; runs comfortably on CPU — no GPU needed early. |
| **Low cost** | Self-hosted → **zero per-call cost**; the budget stays reserved for Claude reasoning. |
| **Quality** | Trained on 1B+ sentence pairs; strong on semantic similarity / retrieval at this size. |
| **Normalized output** | Unit-length vectors → cosine similarity is the natural metric. |
| **SaaS scalable** | Batch on CPU now; move to a GPU worker, an inference endpoint, or a larger model (e.g. `bge-small-en-v1.5`) **behind the same provider interface** later. |

**Alternatives considered:** OpenAI `text-embedding-3-small` (excellent, but a paid API
call per memory — avoidable cost for a private store); larger local models like
`bge-base`/`e5-large` (better recall, heavier — revisit if quality demands it). A dimension
change requires a migration (the DB vector column is fixed at 384), so the model is a
deliberate, locked choice for Phase 1.

> `sentence-transformers` (and `torch`) are an **optional** dependency (`uv sync --extra
> embeddings`), imported lazily. The app, tests, and CI stay lightweight; a deterministic
> **fake provider** backs dev/tests.

---

## 2. Data Model — `memory_embeddings`

One row per `(memory, embedding_model)`; the vector lives beside its provenance.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `memory_id` | UUID FK → memories.id | `ON DELETE CASCADE`; indexed. |
| `embedding_model` | TEXT | Model identity (provenance + multi-model support). |
| `embedding_dimension` | INT | Vector length (sanity + future migrations). |
| `content_hash` | TEXT (sha256) | Of the embedded text → change detection / dedupe. |
| `embedding_vector` | `vector(384)` | pgvector on Postgres; JSON on SQLite (tests). |
| `created_at` | TIMESTAMPTZ | |

**Constraints / indexes:** `UNIQUE(memory_id, embedding_model)`,
`ix_memory_embeddings_memory_id`, and an **HNSW** index
`USING hnsw (embedding_vector vector_cosine_ops)` for fast approximate cosine search.
Enabled by `CREATE EXTENSION IF NOT EXISTS vector` (migration `0003`).

---

## 3. Embedding Lifecycle (the Embedding Service)

```
sync_memory_embedding(memory):
    hash = sha256(memory.content.strip())
    existing = get_embedding(memory_id, model)
    if existing and existing.content_hash == hash:   # ── dedupe: nothing to do
        return existing
    vector = provider.embed_text(memory.content)
    if existing:  update_in_place(vector, hash)      # ── content changed on edit
    else:         create(vector, hash)
```

- **Generate** via the injected `EmbeddingProvider`.
- **Detect change** with a content hash (cheap, no model call to compare).
- **Avoid duplicates** — unchanged content short-circuits before embedding.
- **Update on edit** — a changed memory overwrites its vector in place.

The service flushes through the repository but **does not commit** — the caller owns the
transaction. In production, embedding runs on the **worker tier** (it's model-bound); the
synchronous `POST /memories/{id}/embed` endpoint exists for explicit/ops use and tests.

---

## 4. Semantic Search

`POST /api/v1/memories/search` — body `{ "query": "...", "limit"?, "category"?,
"include_archived"? }`.

```
query → embed_query(query) → search_similar_memories(user_id, query_vector, model, limit)
      → JOIN memories ⋈ memory_embeddings
        WHERE user_id = me AND deleted_at IS NULL AND status = active [AND category]
        ORDER BY embedding_vector <=> query_vector      -- cosine distance (pgvector)
        LIMIT n
      → results ranked nearest-first, similarity_score = 1 − distance
```

- **Tenant-scoped & live-only** by construction (`user_id`, `deleted_at IS NULL`, active).
- **DB-side ranking** via pgvector's `<=>` operator + HNSW index — not Python.
- The `EmbeddingProvider` interface means the query and stored vectors always come from the
  same model; swapping models is an internal change behind `model_name`.

> **Boundary:** search returns *ranked memories*. Turning them into a token-budgeted prompt
> (context assembly) and feeding Claude is **out of scope** here — it's the next layer.

---

## 5. Testing Strategy

pgvector's `<=>` is Postgres-only, so the suite splits cleanly:

- **Embedding logic** (generation, hashing, dedupe, update-on-edit) — runs on in-memory
  SQLite with the fake provider (the vector column degrades to JSON).
- **Search query correctness** — the cosine-ranking statement is **compiled to PostgreSQL
  SQL** and asserted to contain `<=>`, the tenant/`deleted_at`/model filters, `ORDER BY`,
  and `LIMIT` — no database required.
- **Live ranking** — verified against Supabase (pgvector enabled) as a manual/integration
  step; identical query text yields cosine distance ≈ 0 and ranks its memory first.

---

_Related: [memory-system.md](memory-system.md), [database-design.md](database-design.md),
[tech-stack.md](tech-stack.md), [adrs/ADR-003-postgresql-pgvector.md](adrs/ADR-003-postgresql-pgvector.md),
[../docs/phase-1-build-plan.md](../docs/phase-1-build-plan.md)._
