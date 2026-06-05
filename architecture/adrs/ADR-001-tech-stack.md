# ADR-001 — Locked Technology Stack for Phases 0–5

> **Status:** Accepted
> **Date:** Phase 0
> **Deciders:** Founder / CTO, GUMMY OS
> **Supersedes:** —  **Superseded by:** —
> **Re-evaluation trigger:** start of Phase 6, first paying SaaS customer, or sustained
> infra cost > ₹2,000/month.

> This ADR is the decision-record summary of [../tech-stack.md](../tech-stack.md), which
> holds the full per-layer rationale. ADRs 002–004 expand the highest-leverage choices.

---

## Context

GUMMY OS is a solo-founder, memory-centric, multi-agent AI OS, built first for personal
use with a deliberate path to multi-tenant SaaS. The stack must optimize five competing
priorities: **fast solo learning, resume value, AI-engineering relevance, SaaS
scalability,** and a **₹1,000–₹2,000/month budget** (reserved primarily for LLM calls, not
infrastructure). We need one coherent, locked stack so Phase 1 can begin without
relitigating foundational choices mid-build.

## Decision

Lock the following stack for **Phases 0–5**:

| Layer | Choice |
| --- | --- |
| **Frontend** | Next.js (React, TypeScript) + Tailwind + shadcn/ui + Framer Motion |
| **Backend** | Python + FastAPI (async) — see [ADR-004](ADR-004-fastapi-backend.md) |
| **Database** | PostgreSQL via Supabase — see [ADR-003](ADR-003-postgresql-pgvector.md) |
| **Vector store** | pgvector (in Postgres) → Qdrant at scale |
| **Auth** | Supabase Auth + Postgres Row-Level Security |
| **Memory** | Custom Memory Service over Postgres + pgvector (the moat — [ADR-002](ADR-002-memory-first.md)) |
| **AI models** | Claude (Haiku + Sonnet/Opus) behind a provider-abstracted LLM gateway |
| **Agent framework** | Lightweight custom orchestration on the Anthropic SDK |
| **Search** | pgvector + Postgres full-text (internal); Tavily/Brave (web, Phase 4+) |
| **Storage** | Supabase Storage (S3-compatible) |
| **Deployment** | Vercel (FE) + Render/Railway/Fly.io (BE + workers) + Docker |
| **Observability** | Sentry + Langfuse (LLM tracing) + structured logs |
| **Analytics** | PostHog (analytics + feature flags) |
| **Dev workflow** | GitHub + Actions CI, monorepo, Ruff/Black + ESLint/Prettier, pytest + Playwright |

**Cross-cutting principles** (from [CONVENTIONS.md §6](../../CONVENTIONS.md)): multi-tenant
(`user_id`-scoped) from day one; stateless services + stateful stores; clean swappable
seams (Memory Service, LLM gateway, storage, auth) to avoid lock-in.

## Consequences

**Positive**
- One database does relational + vector + full-text → minimal moving parts for one person.
- TypeScript ↔ Python boundary is a clean REST/streaming API contract.
- Every component has a documented, no-rewrite migration path to scale.
- Free tiers cover infra; budget is reserved for LLM calls (the real variable cost).

**Negative / accepted**
- Two languages in one repo (TS + Python) — accepted; each is best-in-class for its job.
- Some vendor conveniences (Supabase, Claude caching) create mild coupling — contained
  behind abstraction seams.
- Next.js App Router + Python async both carry a learning curve — accepted for resume value.

## Alternatives Considered

- **Node/NestJS unified backend** — one language, but a shallower AI/agent/RAG ecosystem
  than Python.
- **Next.js API routes only (no separate backend)** — simplest start, but couples
  long-running agent jobs to the web tier; likely rewrite.
- **AWS/GCP from day one / Kubernetes** — maximal power and ops burden; premature and a
  surprise-bill risk for a solo dev.
- **Managed memory frameworks / heavy agent frameworks** — faster to demo, but outsource
  the exact differentiators we want to own (see ADR-002, [../tech-stack.md §8](../tech-stack.md)).

---

_Full rationale: [../tech-stack.md](../tech-stack.md). Realizes
[../system-design.md](../system-design.md) and [../../docs/ROADMAP.md](../../docs/ROADMAP.md)._
