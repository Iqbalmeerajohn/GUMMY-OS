# Architecture Decision Records (ADRs)

> Immutable log of the **significant** architecture decisions behind GUMMY OS — the *why*
> behind the *what*. Per [CONVENTIONS.md §6](../../CONVENTIONS.md), we document decisions,
> not just outcomes.

An ADR captures a single decision: its **context**, the **decision**, the **alternatives**
weighed, and the **consequences** accepted. ADRs are **append-only** — we don't rewrite
history; we supersede a record with a newer one and update its status.

## Format

Each ADR follows: **Title · Status · Context · Decision · Consequences · Alternatives**.
Statuses: `Proposed` → `Accepted` → (`Superseded by ADR-NNN` | `Deprecated`).

## Index

| ADR | Title | Status |
| --- | --- | --- |
| [ADR-001](ADR-001-tech-stack.md) | Locked technology stack for Phases 0–5 | Accepted |
| [ADR-002](ADR-002-memory-first.md) | Build the memory system first (memory is the moat) | Accepted |
| [ADR-003](ADR-003-postgresql-pgvector.md) | PostgreSQL + pgvector as the unified data + vector store | Accepted |
| [ADR-004](ADR-004-fastapi-backend.md) | Python + FastAPI for the backend & agent runtime | Accepted |

> The detailed, narrative form of the full stack lives in
> [../tech-stack.md](../tech-stack.md); ADR-001 is its decision-record summary. ADRs
> 002–004 record the load-bearing choices that everything else depends on.
