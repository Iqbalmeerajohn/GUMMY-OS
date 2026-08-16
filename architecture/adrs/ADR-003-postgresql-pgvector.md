# ADR-003 — PostgreSQL + pgvector as the Unified Data + Vector Store

> **Status:** Accepted
> **Date:** Phase 0
> **Deciders:** Founder / CTO, GUMMY OS
> **Supersedes:** —  **Superseded by:** —

> **M9 note:** the decision itself stands — Postgres + pgvector is still the
> unified store. Only the hosting changed: local Postgres 16 in Docker instead
> of managed Supabase. See
> [M9 — Local-First GUMMY](../../docs/10_RELEASE_NOTES_M9_LOCAL_FIRST.md).
> **Relates to:** [ADR-002 (memory-first)](ADR-002-memory-first.md),
> [ADR-001 (stack)](ADR-001-tech-stack.md)

---

## Context

The memory layer ([ADR-002](ADR-002-memory-first.md)) needs both **structured, relational,
multi-tenant data** (`users`, `conversations`, `messages`, `memories`, `documents`, `jobs`,
`research_reports`, `settings`) and **vector similarity search** over embeddings for
semantic recall. The data model is explicitly multi-tenant (`user_id` everywhere) and
SaaS-bound (see [../database-design.md](../database-design.md)).

The naive approach uses two systems — a relational DB *plus* a dedicated vector DB
(Pinecone/Qdrant/…). For a solo founder on a tight budget, that means two sources of truth,
two bills, two backup stories, and the inability to filter-and-rank in a single query.

## Decision

Use **PostgreSQL** as the single system of record, with the **pgvector** extension storing
embeddings *alongside* their source rows. Run it **managed via Supabase** in early phases
(which also provides Auth, Storage, and RLS on the same Postgres).

- Embeddings stored as `vector` columns next to source text; ANN indexes (HNSW/IVFFlat).
- **Hybrid retrieval in one SQL query:** relational filters (`user_id`, `type`, recency,
  importance/confidence) + vector similarity + Postgres full-text (`tsvector`).
- **Row-Level Security** enforces tenant isolation as defense-in-depth.
- The Memory Service abstracts retrieval so the engine can be swapped later.

## Consequences

**Positive**
- **One database, one backup, one bill, one mental model** — minimal moving parts for a
  solo dev; eliminates an entire external service during budget-sensitive phases.
- **Private, tenant-scoped recall** that mixes similarity with relational filters in a
  single query — exactly what memory recall needs (and hard to do across two systems).
- Postgres is the most respected, battle-tested relational core for multi-tenant SaaS, with
  strong JSONB for forward-compatible schema evolution.
- RLS + `user_id` scoping make multi-tenancy a first-class, auditable property.

**Negative / accepted**
- pgvector trails a dedicated engine at *very* large scale / high QPS — accepted; we are far
  from that, and pgvector with HNSW is excellent into the millions of vectors.
- Managed free-tier Postgres has connection/compute limits — mitigated with connection
  pooling (PgBouncer / Supabase pooler; pooled vs. direct URLs in `.env.example`).
- Mild Supabase convenience lock-in — contained because the core is *just Postgres* and
  portable to Neon/RDS/Cloud SQL without schema changes.

## Alternatives Considered

- **Postgres + a separate vector DB (Pinecone/Qdrant/Weaviate)** — better at extreme scale,
  but two sources of truth, extra cost, and no single-query hybrid retrieval early.
- **MongoDB** — flexible documents, but our model is relational + multi-tenant; we'd fight
  the document model and lose strong integrity and RLS.
- **MySQL/MariaDB** — fine, but weaker JSONB and no first-class vector story.
- **SQLite** — perfect for local dev, wrong for the multi-tenant SaaS target.

## Future Scalability

Read replicas; partition hot tables (`messages`, `memories`, `document_chunks`) by
`user_id`/time; migrate embeddings to **Qdrant** behind the Memory Service interface when
vector volume/QPS demands it (an internal swap, not a rewrite); migrate off Supabase to
managed Postgres if needed — schema unchanged.

---

_Realizes [../database-design.md](../database-design.md) and
[../tech-stack.md §3–4](../tech-stack.md)._
