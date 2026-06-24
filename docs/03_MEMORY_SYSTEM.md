# 03 — Memory System

Memory is GUMMY's defining capability: Gummy learns durable facts from
conversation and recalls them later, even in unrelated threads.

## How memory works (end to end)

```
conversation turn
      │
      ▼
extraction ──► candidate memories ──► storage (memories + sources + versions)
                                            │
                                            ▼
                                   embedding worker ──► memory_embeddings (pgvector)
                                            │
new turn ──► retrieval (cosine similarity, tenant-scoped) ──► context ──► grounded reply
                                            │
                                            ▼
                                   "Memory Used" disclosure (content only)
```

## Extraction pipeline

`services/conversation/memory_extraction_service.py` inspects conversation turns
and proposes candidate memories with a category (profile, preference, project,
career, learning, …) and importance/confidence scores. An **extraction watermark**
(migration 0011) tracks how far a conversation has been processed so extraction is
incremental and never re-processes the same turns.

## Storage pipeline

- `memories` — the durable record (content, category, importance, confidence, status).
- `memory_versions` — history of edits, so changes are auditable.
- `memory_sources` (migration 0009) — provenance: which conversation/message a
  memory came from, enabling source tracking in the UI.
- Soft delete (migration 0002): memories are deactivated/archived rather than hard-deleted.

## Embedding pipeline

`services/embeddings/` + `embedding_worker` generate a vector per memory, stored in
`memory_embeddings` keyed by `embedding_model` and a `content_hash`. Keying on the
model name lets the system run multiple embedding models and re-embed safely; the
content hash makes embedding idempotent (no duplicate work for unchanged content).

## Retrieval pipeline

`repositories/search_repository.py` builds a tenant-scoped statement that joins
`memories` → `memory_embeddings` and orders by pgvector cosine distance (`<=>`),
filtered to live (non-deleted) rows and, by default, active status. Retrieval is a
single ranked SQL query (no per-row round-trips) and returns `(memory, distance)`
pairs nearest-first. Distance is converted to a similarity score for the API.

## Cross-conversation recall

Because retrieval ranks over *all* of a user's memories — not just the current
thread — facts learned in one conversation surface in another. On each turn the
turn service embeds the incoming query, retrieves the top memories, injects them
into the model context, and returns their contents in the terminal `done` SSE
frame. The workspace renders these under a collapsible **“Memory Used”** control.

## RLS security model

Every memory-related table is protected by PostgreSQL **Row-Level Security**
(migration 0005). Policies scope rows to their owning user, so tenant isolation is
enforced by the database itself — not merely by application `WHERE user_id = …`
clauses.

- **Request path:** the JWT (verified in `core/security.py`) yields a user id that
  is set as the tenant context for the session.
- **Worker path:** background workers set the same tenant context explicitly
  (`core/tenant_context.py`) before querying, so they observe identical policies.
- **Defense in depth:** application queries still filter by `user_id`; RLS is the
  backstop that makes a missing filter fail safe instead of leaking data.

## Privacy guarantees in the UI

The Memory Center and “Memory Used” disclosure expose **content only**. Raw
embedding vectors and similarity scores are intentionally never returned to or
rendered in the client.
