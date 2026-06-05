# ADR-002 — Build the Memory System First (Memory Is the Moat)

> **Status:** Accepted
> **Date:** Phase 0
> **Deciders:** Founder / CTO, GUMMY OS
> **Supersedes:** —  **Superseded by:** —
> **Relates to:** [ADR-003 (Postgres + pgvector)](ADR-003-postgresql-pgvector.md),
> [ADR-004 (FastAPI)](ADR-004-fastapi-backend.md)

---

## Context

GUMMY OS is a team of specialized agents (Career, Learning, Research, Builder, …) backed by
a persistent, consent-based long-term memory. We must decide **what to build first** —
agents that deliver visible value quickly, or the memory layer they all depend on.

Two facts force the decision:

1. **Every agent is only as good as what it remembers.** An agent without durable,
   user-scoped recall is a generic chatbot. Memory is the product's differentiation — its
   *moat* — and the thing that makes Gummy feel like it *knows you*.
2. **Memory is the highest-leverage AI-engineering skill** in this project (hybrid
   retrieval, embeddings, summarization/compaction, consent) and the biggest resume payoff.

The [ROADMAP](../../docs/ROADMAP.md) sequences phases by **dependency**, not value-timing,
and the data model is already designed **memory-centric and multi-tenant** (see
[../database-design.md](../database-design.md)).

## Decision

**Build the memory system as Phase 1, before any specialized agent**, as a **custom Memory
Service** that we own — not an outsourced memory framework.

Phase 1 delivers:

- The core data model: `users`, `conversations`, `messages`, `memories`, `documents`
  (+ `document_chunks`) — see [../database-design.md](../database-design.md).
- **Short-term** (conversation) + **long-term** (semantic) memory.
- An embeddings pipeline and **hybrid retrieval** (vector similarity + relational filters
  on `user_id`, type, recency, importance/confidence).
- Write path (capture), recall path (retrieval), and summarization/compaction.
- Document ingestion: upload → parse → chunk → embed → index.

The Memory Service is exposed as a **stable internal interface** so agents (Phase 2+) call
it without knowing its internals, and so the storage engine can evolve underneath it.

## Consequences

**Positive**
- Phase 2+ agents inherit recall "for free" through one well-tested interface — they compose
  rather than each reinventing context handling.
- We own and understand the moat; full control over **cost** (context trimming, caching)
  and **quality** of what the LLM sees.
- Consent, provenance, and "forgetting" (soft deletes) are designed in from the first line,
  satisfying the privacy-first promise and the [security model](../security-system.md).
- The Memory Center UX ("you own your memory") has a real backend to render.

**Negative / accepted**
- **Slower time-to-first-visible-agent** — Phase 1 ships infrastructure, not a flashy agent.
  Accepted: it is the foundation everything else stands on.
- More to build and maintain than adopting Mem0/Zep/Letta — accepted deliberately; this is
  the project's reason to exist and its core learning goal.
- Requires getting retrieval quality right early (the riskiest core) — mitigated by
  meaningful tests on scoring/retrieval per [CONVENTIONS.md §7](../../CONVENTIONS.md).

## Alternatives Considered

- **Career Agent first (value-first ordering)** — high immediate personal value, but it
  would be built on a stand-in memory and likely rewritten once real memory exists.
- **Adopt a managed memory framework (Mem0 / Zep / Letta/MemGPT)** — fast, but outsources
  the exact differentiator and the skill we most want to build.
- **LangChain memory abstractions** — convenient but leaky and limiting for a bespoke,
  multi-tier, consent-based design.

---

_Realizes [../memory-system.md](../memory-system.md) and
[../database-design.md](../database-design.md); sequenced by
[../../docs/ROADMAP.md](../../docs/ROADMAP.md) (Phase 1)._
