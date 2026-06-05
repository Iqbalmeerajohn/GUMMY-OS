# ADR-004 — Python + FastAPI for the Backend & Agent Runtime

> **Status:** Accepted
> **Date:** Phase 0
> **Deciders:** Founder / CTO, GUMMY OS
> **Supersedes:** —  **Superseded by:** —
> **Relates to:** [ADR-001 (stack)](ADR-001-tech-stack.md),
> [ADR-002 (memory-first)](ADR-002-memory-first.md)

---

## Context

GUMMY OS needs a backend that hosts the API, the **Memory Service**, the **LLM gateway**,
and the **agent runtime** (Master Orchestrator + specialized agents). The frontend is
Next.js/TypeScript ([ADR-001](ADR-001-tech-stack.md)), so the backend language is a genuine
choice. The dominant workloads are **I/O-bound LLM/DB/network calls**, **streaming**
token-by-token responses, and **typed agent I/O contracts**. The single most strategic lens
is **AI-engineering relevance** — the project exists partly to build exactly these skills.

## Decision

Use **Python + FastAPI (async)** as a backend **separate** from the Next.js app.

- **Python** is the lingua franca of AI engineering: every LLM/agent/RAG SDK (the Anthropic
  SDK included), tool, and tutorial targets it first.
- **FastAPI** is async-native — ideal for I/O-bound LLM workloads — with first-class
  streaming, auto-generated OpenAPI docs, and **Pydantic** models.
- **Pydantic** doubles as the **typed I/O contract for agents** described in the
  [agent framework](../agent-framework.md) and [system design](../system-design.md).
- Services are **stateless**; durable state lives in Postgres (see
  [ADR-003](ADR-003-postgresql-pgvector.md)). Long-running/headless work (e.g. Playwright,
  Phase 7) goes to a **worker tier**, not the web request path.
- Standards: Black + Ruff, type hints everywhere, async-first I/O, pytest
  (see [CONVENTIONS.md §7](../../CONVENTIONS.md)).

## Consequences

**Positive**
- Direct access to the deepest AI/agent/RAG ecosystem — the highest-leverage choice for the
  project's core skill-building and resume value.
- Async + streaming match the "JARVIS typing" UX and LLM latency profile.
- Pydantic gives one typed contract shared by the API, the agents, and the docs.
- Stateless FastAPI scales horizontally behind a load balancer; a clean REST/streaming
  boundary keeps the TS↔Python seam simple.

**Negative / accepted**
- **Two languages in the repo** (TypeScript frontend, Python backend) — accepted; each is
  best-in-class for its job and the boundary is a clean API contract.
- Python concurrency needs discipline (async + a worker queue for CPU/long jobs) — addressed
  by the stateless-service + worker-tier design.
- A separate backend is more deploy surface than Next.js API routes — accepted to avoid
  coupling long-running agent jobs to the web tier (which would force a later rewrite).

## Alternatives Considered

- **Next.js API routes only (no separate backend)** — simplest start and one language, but
  couples long-running agent jobs to the web tier and caps scalability; a likely rewrite.
- **Node.js / NestJS** — one language with the frontend and strong, but Python's AI/agent
  ecosystem is deeper and more mature — the decisive factor here.
- **Go** — superb performance and ops story, but slower AI iteration and a steeper curve for
  a solo, AI-focused dev.

## Future Scalability

Horizontal scale of stateless FastAPI services behind a load balancer; offload long/headless
jobs to a worker queue; graduate hosting from PaaS (Render/Railway/Fly.io + Docker) to a VPS
cluster or Cloud Run/ECS when traffic justifies it — containers make the move low-risk.

---

_Realizes [../system-design.md](../system-design.md),
[../agent-framework.md](../agent-framework.md), and [../tech-stack.md §2](../tech-stack.md)._
