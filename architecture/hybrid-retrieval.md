# GUMMY OS — Hybrid Retrieval Engine

> How a query becomes a ranked set of memories: semantic similarity blended with
> importance, confidence, and recency — plus reinforcement and automatic embedding
> sync. This is the layer that decides *what Gummy remembers right now*.

> **Scope:** Phase 1, Day 5 — hybrid ranking, reinforcement, and the auto-embed
> worker **only**. No context assembly, RAG, or Claude reasoning (the next layer).
> **Status:** Implemented. Builds on
> [embeddings-and-search.md](embeddings-and-search.md) and
> [memory-system.md §4, §6](memory-system.md).

---

## 1. The Hybrid Ranking Formula

For each candidate memory, four signals are combined into one score in **[0, 1]**:

```
final = w_sem · semantic_similarity      (relevance to the query)
      + w_imp · importance_score         (how much it matters)
      + w_conf · confidence_score        (how sure we are it's true)
      + w_rec · recency_score            (how fresh / recently used)
```

| Weight | Value | Why |
| --- | --- | --- |
| `w_sem` | **0.55** | Relevance dominates — prevents surfacing important-but-unrelated memories. |
| `w_imp` | **0.20** | Lets identity/goals/active projects win close ties. |
| `w_rec` | **0.15** | Favors current truth; old facts fade unless reinforced. |
| `w_conf` | **0.10** | Gently demotes uncertain/inferred memories. |

Weights **sum to 1.0**, so the final score stays in [0, 1] and is directly
comparable. All inputs are clamped to [0, 1] (cosine similarity can be negative).

**Recency** uses exponential decay with a 30-day half-life:
`recency = 0.5 ^ (age_days / 30)`, where age is measured from `last_recalled_at`
(falling back to `created_at`). So a memory recalled today scores ~1.0; one untouched
for a month, ~0.5.

> **Why this shape?** It directly targets the two classic failure modes from
> [memory-system.md §4.3](memory-system.md): "forgot the obvious" (importance/recency
> rescue relevant-but-not-top-similarity memories) and "drowned in trivia" (semantic
> weight keeps off-topic memories down). Weights live in `core/constants.py` and are
> tunable / A/B-able without code changes.

### Pipeline

```
query → embed → semantic candidates (pgvector, over-fetch ×4)
      → score each by the hybrid formula → sort desc → take top-K
      → reinforce the survivors → return
```

Over-fetching (`limit × 4`) gives the hybrid re-rank room to promote a memory that
isn't the single closest vector but wins on importance/recency.

---

## 2. Reinforcement — memories that get used get "stickier"

Retrieving a memory makes it more likely to surface again, mirroring how human memory
strengthens with recall. For each memory actually returned:

- `recall_count += 1` and `last_recalled_at = now` (always).
- `importance_score` and `confidence_score` get a **diminishing** bump:
  `new = old + STEP · (1 − old)` (importance STEP 0.05, confidence STEP 0.03).

### Safeguards (anti-runaway)

| Safeguard | Effect |
| --- | --- |
| **Diminishing step** | Bumps shrink as a score approaches 1.0 — asymptotic, never overshoots. |
| **Hard cap** | `min(1.0, …)` guarantees the [0, 1] invariant. |
| **Cooldown (60 s)** | Score bumps happen at most once per window, so a burst of retrievals (or a retry loop) can't inflate a memory. The recall is still *counted*. |

This keeps reinforcement honest: genuinely useful memories rise slowly over many
sessions; gaming via rapid repeated queries does nothing.

---

## 3. Automatic Embedding Sync

Embeddings stay current **without manual `/embed` calls**. On memory **create** and
**update**, the memory service enqueues a job; a background worker (re)embeds it. The
embedding service dedupes by content hash, so an update that didn't change content is a
no-op.

```
create/update memory ──▶ embedding_worker.enqueue(memory_id, user_id)
                              │ (in-process asyncio.Queue)
                              ▼
                      worker drains ──▶ sync_memory_embedding(memory)
```

The synchronous `POST /memories/{id}/embed` endpoint remains for explicit/ops use, but
the happy path is automatic.

---

## 4. Background Worker Design (lightweight)

A single asyncio task drains an in-memory queue — **no Redis/Celery** in Phase 1.

| Concern | Design |
| --- | --- |
| **Queue** | `asyncio.Queue` of `EmbeddingJob(memory_id, user_id)`. |
| **Processing** | Each job runs in its **own DB session**, committed independently. |
| **Retries** | Up to `EMBEDDING_MAX_RETRIES` (3) with exponential backoff (`0.5·2ⁿ`). |
| **Failure handling** | After retries, log and **drop** the job — the worker never crashes; the next job proceeds. |
| **Lifecycle** | Configured + started in the app lifespan (when a DB is present), stopped on shutdown. |
| **Idle safety** | `enqueue()` is a no-op when the worker isn't running (e.g. tests). |

**Scale path:** the queue/worker is an internal seam. When volume justifies it, swap the
`asyncio.Queue` for Redis + a separate worker process (or Celery/RQ) without touching the
memory service or the retrieval engine.

---

## 5. API

`POST /api/v1/memories/retrieve` — body `{ "query": "...", "limit"?, "category"?,
"include_archived"?, "reinforce"? }` → top-ranked memories, each with its full score
breakdown (`semantic_similarity`, `recency_score`, `final_score`, `recall_count`).

> **Boundary:** retrieval returns *ranked memories*. Assembling them into a
> token-budgeted prompt and calling Claude is the **next** layer — deliberately out of
> scope here.

---

## 6. Testing Strategy

- **Ranking math** (weights, recency decay, clamping, diminishing reinforcement) — pure
  unit tests, no database.
- **Reinforcement** (cooldown, caps, recall counting) — SQLite.
- **Retrieval orchestration** — exercised over HTTP on SQLite with the pgvector candidate
  fetch monkeypatched (the `<=>` ranking itself is covered in
  [embeddings-and-search.md](embeddings-and-search.md)).
- **Worker** — processes a job, survives a failing job (retry → drop), and is a no-op
  when idle.

---

_Related: [embeddings-and-search.md](embeddings-and-search.md),
[memory-system.md](memory-system.md), [database-design.md](database-design.md),
[../docs/phase-1-build-plan.md](../docs/phase-1-build-plan.md)._
