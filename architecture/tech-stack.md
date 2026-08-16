# GUMMY OS — Technology Stack (Phase 0 → Phase 5)

> **Author:** CTO, GUMMY OS
> **Status:** Locked for Phases 0–5 (Foundation → Builder Agent).
> **Re-evaluation trigger:** Start of Phase 6, or first paying SaaS customer, or
> sustained infra cost > ₹2,000/month.
>
> **Superseded in part by [M9 — Local-First GUMMY](../docs/10_RELEASE_NOTES_M9_LOCAL_FIRST.md).**
> Every hosted row below (Supabase, Vercel, Railway, Sentry, PostHog) was removed
> in M9; GUMMY now runs entirely on the user's machine. The language, framework,
> database, and vector-store decisions still hold. Read the hosting sections as
> the reasoning that led here, not as current state.

This document finalizes the technology stack for the first six phases of GUMMY OS. It is
written as a series of **architecture decisions**: each choice states *why it was
selected*, *what alternatives were considered*, the *tradeoffs accepted*, and the *future
scalability* path.

### Decision Lens

Every choice below is scored against the founder's five priorities:

| Priority | What it means here |
| --- | --- |
| 🎓 **Fast learning (solo dev)** | One person must ship it; minimize moving parts and context-switching. |
| 💼 **Resume value** | Technologies a hiring manager respects and that signal seniority. |
| 🤖 **AI engineering relevance** | Skills directly transferable to LLM/agent/RAG roles. |
| 📈 **SaaS scalability** | Won't need a rewrite when we go multi-tenant and grow. |
| 💰 **Low cost (₹1,000–₹2,000/mo)** | ~$12–24/month all-in for the personal/early phase. |

> **Cost reality check:** the dominant variable cost in Phases 1–5 is **LLM API usage**,
> not infrastructure. The stack is deliberately built on free/near-free tiers for
> hosting, DB, and storage so the budget is reserved almost entirely for model calls.

---

## 1. Frontend

**Decision: Next.js (React, TypeScript) + Tailwind CSS + shadcn/ui.**

1. **Why selected**
   - One framework covers UI, routing, and lightweight backend-for-frontend (API
     routes), reducing surface area for a solo dev.
   - TypeScript end-to-end means shared types with the backend contract.
   - Tailwind + shadcn/ui gives a professional, modern UI fast without a design team.
   - Excellent streaming support (Server Components, `streamText`) — essential for the
     token-by-token "JARVIS typing" feel.
2. **Alternatives considered**
   - **Plain React + Vite:** simpler mental model, but no SSR/routing/streaming
     batteries — more glue code over time.
   - **SvelteKit:** great DX, smaller bundles, but a smaller ecosystem and weaker
     resume signal in the AI/SaaS job market.
   - **Vue/Nuxt:** capable, but React dominates the AI-app ecosystem (Vercel AI SDK,
     examples, hiring demand).
3. **Tradeoffs**
   - Next.js has real complexity (App Router, RSC mental model) — a learning curve.
   - Risk of over-engineering the frontend early; mitigated by keeping it a thin client
     over the backend API.
4. **Future scalability**
   - Scales to a full SaaS marketing site + app in one codebase; deploys to Vercel's
     edge/CDN trivially. React Native (Phase 13) reuses React skills and component logic.

---

## 2. Backend

**Decision: Python + FastAPI.**

1. **Why selected**
   - **Python is the lingua franca of AI engineering** — every LLM/agent/RAG library,
     SDK, and tutorial targets it first. This is the single highest-leverage choice for
     AI engineering relevance.
   - FastAPI is async-native (ideal for LLM I/O-bound workloads), fast, and gives
     auto-generated OpenAPI docs and typed request/response models (Pydantic).
   - Pydantic doubles as the **typed I/O contract for agents** described in the system
     design.
2. **Alternatives considered**
   - **Node.js (NestJS):** one language with the frontend; strong, but the AI ecosystem
     in Python is deeper and the agent/RAG tooling is more mature there.
   - **Next.js API routes only (no separate backend):** simplest to start, but couples
     long-running agent jobs to the web tier and caps scalability — a likely rewrite.
   - **Go:** superb performance and ops story, but slower AI iteration and a steeper
     curve for a solo AI-focused dev.
3. **Tradeoffs**
   - Two languages in the repo (TS frontend, Python backend) — accepted, because each is
     best-in-class for its job and the boundary is a clean REST/streaming API.
   - Python concurrency requires discipline (async + workers) — addressed in §7/§13.
4. **Future scalability**
   - Stateless FastAPI services scale horizontally behind a load balancer; long jobs go
     to a worker queue (§7-adjacent). This is a well-trodden SaaS path.

---

## 3. Database

**Decision: PostgreSQL (managed — Supabase in early phases).**

1. **Why selected**
   - The most respected, battle-tested relational DB; the safe long-term core for a
     multi-tenant SaaS data model (matches `database-design.md` exactly).
   - **pgvector** lets Postgres also serve as the vector store early (see §4) — one
     fewer system to run and pay for.
   - **Supabase** wraps Postgres with auth, storage, and a generous free tier — a
     force-multiplier for a solo dev on a tight budget.
2. **Alternatives considered**
   - **MySQL/MariaDB:** fine, but weaker JSONB and no first-class vector story.
   - **MongoDB:** flexible, but our model is relational and multi-tenant; we'd fight the
     document model and lose strong integrity/RLS.
   - **SQLite:** perfect for local dev, but not the multi-tenant SaaS target.
3. **Tradeoffs**
   - Managed Postgres on a free tier has connection/compute limits; mitigated with
     connection pooling (PgBouncer/Supabase pooler).
   - Mild lock-in to Supabase conveniences; mitigated because the core is *just Postgres*
     and portable.
4. **Future scalability**
   - Read replicas, partitioning of hot tables (`messages`, `memories`,
     `document_chunks`), and RLS for tenant isolation. Migrate off Supabase to managed
     Postgres (RDS/Neon/Cloud SQL) without schema changes if needed.

---

## 4. Vector Database

**Decision: pgvector (inside Postgres) now → dedicated vector DB later (Qdrant) at scale.**

1. **Why selected**
   - Keeping vectors *in Postgres* means **one database, one backup, one bill, hybrid
     queries** (relational filters + similarity in a single SQL query) — exactly what the
     memory layer needs for private, tenant-scoped recall.
   - Eliminates an entire external service during the budget-sensitive early phases.
2. **Alternatives considered**
   - **Pinecone:** excellent managed vector DB and great resume keyword, but a paid
     service that adds cost and a second source of truth early.
   - **Qdrant / Weaviate / Milvus:** powerful, self-hostable; overkill until vector
     volume and latency demand a specialized engine.
   - **Chroma:** great for local prototyping, weaker as a production multi-tenant store.
3. **Tradeoffs**
   - pgvector is excellent up to millions of vectors with HNSW indexing, but a dedicated
     engine wins at very large scale / high QPS. Accepted — we are nowhere near that.
4. **Future scalability**
   - Clean migration path: when scale demands it, move embeddings to **Qdrant**
     (self-host cheap, or managed) while Postgres remains the system of record. The
     Memory Service abstracts retrieval, so this is an internal swap, not a rewrite.

---

## 5. Authentication

**Decision: Supabase Auth (early) with a provider-abstracted boundary.**

1. **Why selected**
   - Ships email/password + OAuth (Google, etc.), JWT issuance, and integrates natively
     with Postgres **Row-Level Security** — directly enabling the tenancy model in the
     system design.
   - Zero extra cost on the free tier; minimal code for a solo dev.
2. **Alternatives considered**
   - **Clerk:** superb DX and pre-built UIs, but paid scaling and another vendor.
   - **Auth0:** enterprise-grade, but heavier and pricier than needed early.
   - **Roll-your-own JWT:** maximum control, maximum footguns (security risk for a solo
     dev) — explicitly rejected.
3. **Tradeoffs**
   - Coupling to Supabase Auth; mitigated by treating auth as a boundary (verify JWTs at
     the API Gateway, keep our own `users` row as the source of truth).
4. **Future scalability**
   - RLS-backed multi-tenancy scales to SaaS. If we outgrow Supabase Auth, swapping to
     Clerk/Auth0/Cognito is contained because the app trusts a verified token + local
     `users` table, not the provider's internals.

---

## 6. Memory Layer

**Decision: Custom memory service over Postgres + pgvector (own the moat; don't outsource it).**

1. **Why selected**
   - Memory is explicitly the product's moat — building it ourselves is the **core AI
     engineering skill** of this project and the highest-leverage thing to learn.
   - Combines structured rows (`memories`, `messages`, summaries) with vector recall in
     one store; supports hybrid retrieval (similarity + recency + importance filters).
   - LLM-driven summarization/compaction handled in our own pipeline for full control of
     cost and quality.
2. **Alternatives considered**
   - **Mem0 / Zep / Letta (MemGPT):** managed/opinionated memory frameworks — great for
     speed, but outsource the exact differentiator we want to own and understand.
   - **LangChain memory abstractions:** convenient, but leaky and limiting for a bespoke,
     multi-tier memory design.
3. **Tradeoffs**
   - More to build and maintain than adopting a library — accepted deliberately, because
     this *is* the project's reason to exist and its biggest learning/resume payoff.
4. **Future scalability**
   - The Memory Service interface stays stable while internals evolve (add Qdrant, add
     caching, add a graph layer for relationships) without touching agents.

---

## 7. AI Models

**Decision: Claude (Anthropic) as primary, behind a provider-abstracted LLM gateway, with
a cheap model tier for routine work.**

1. **Why selected**
   - **Claude** offers top-tier reasoning, agentic tool-use, and large context — ideal
     for an orchestrator + multi-agent system, and the model family this project is built
     around. Prompt caching meaningfully cuts cost on repeated context (e.g. system
     prompts, memory).
   - A **tiered strategy** controls the budget: a small/fast model (e.g. **Claude
     Haiku**) for routing, summarization, and high-volume cheap tasks; a frontier model
     (**Claude Sonnet/Opus**) for hard reasoning, research, and building.
   - A **provider-abstracted gateway** keeps us free to mix in others where economical.
2. **Alternatives considered**
   - **OpenAI GPT family:** excellent and ubiquitous; kept as a swappable secondary via
     the gateway for benchmarking/fallback.
   - **Local/open models (Llama, Mistral via Ollama):** ~zero marginal cost and great for
     learning, but ops/quality overhead; reserved for cheap background tasks later.
   - **Google Gemini:** strong long-context option; viable secondary via the gateway.
3. **Tradeoffs**
   - LLM calls are the **main budget line** — managed via model tiering, prompt caching,
     aggressive context trimming (the memory layer earns its keep here), and per-user
     usage caps.
   - Some vendor coupling to Claude features (e.g. caching); contained by the gateway.
4. **Future scalability**
   - The gateway enables per-agent, per-task model selection and cost-based routing
     across providers — a core AI-engineering capability and a real cost lever at scale.

> **Always confirm exact model IDs, pricing, and limits from current Anthropic docs
> before locking spend** — do not hardcode assumptions about model economics.

---

## 8. Agent Framework

**Decision: Lightweight, mostly custom orchestration (Anthropic SDK + thin tooling), avoid
heavy frameworks early.**

1. **Why selected**
   - Building the orchestrator + agent contract ourselves teaches the **fundamentals of
     agentic systems** (routing, tool-calling, context assembly, composition) — exactly
     the resume-defining, transferable AI-engineering skill.
   - Avoids premature lock-in to a framework's abstractions; keeps the system debuggable
     and cheap.
   - The **Anthropic SDK** (native tool-use) plus small, typed helpers covers Phases 2–5.
2. **Alternatives considered**
   - **LangChain / LangGraph:** powerful (LangGraph's state machines are genuinely good
     for multi-agent flows) and resume-relevant, but heavy and fast-changing; risks
     hiding the fundamentals while you're still learning them.
   - **CrewAI / AutoGen:** quick multi-agent demos, but opinionated and harder to bend to
     a bespoke memory-centric design.
   - **LlamaIndex:** strong for RAG/ingestion specifically; may adopt *just its
     ingestion/retrieval pieces* selectively.
3. **Tradeoffs**
   - More upfront building vs. instant multi-agent scaffolding — accepted for learning
     depth and control.
   - We may revisit **LangGraph** for complex Phase 4/5 multi-step workflows once the
     fundamentals are internalized.
4. **Future scalability**
   - A clean agent contract means we can adopt LangGraph (or keep custom) per-workflow
     without rewriting agents — and it's the foundation for the Phase 14 agent ecosystem.

---

## 9. Search Layer

**Decision: Hybrid search in Postgres (pgvector semantic + native full-text) now;
external web search via API for the Research/Browser agents.**

1. **Why selected**
   - **Internal knowledge search** (memories, documents) is best served by combining
     pgvector similarity with Postgres full-text (`tsvector`) — hybrid retrieval beats
     either alone and needs **no new infrastructure**.
   - **External web search** for the Research Agent (Phase 4) is handled via a search API
     (e.g. **Tavily**, built for LLM/agent use, or Brave Search API) — pay-per-use and
     cheap at personal volume.
2. **Alternatives considered**
   - **Elasticsearch / OpenSearch / Meilisearch / Typesense:** excellent dedicated search
     engines, but another service to run and fund — unjustified until scale demands it.
   - **SerpAPI / Google Programmable Search:** viable web-search options; Tavily is more
     LLM-native and predictable in cost.
3. **Tradeoffs**
   - Postgres full-text is very good but not a specialized search engine — fine for our
     volumes; revisit at scale.
   - External search adds a small variable cost and rate limits — capped per user.
4. **Future scalability**
   - Promote internal search to Meilisearch/Typesense (cheap, fast) or OpenSearch if/when
     query volume justifies it; the retrieval interface hides the change.

---

## 10. Browser Automation

**Decision: Playwright (deferred to Phase 7, but locked now for planning).**

1. **Why selected**
   - The modern standard for reliable headless automation: auto-waiting, multi-browser,
     strong anti-flakiness, and Python bindings that fit our backend.
   - Powers the Browser Agent's safe, sandboxed web actions and feeds Research/Career.
2. **Alternatives considered**
   - **Puppeteer:** great but Chromium-only and JS-first (would mean Node in the worker).
   - **Selenium:** mature but older DX and flakier than Playwright.
   - **Hosted browser APIs (Browserbase, etc.):** zero-ops and scalable, but recurring
     cost — consider later if self-hosting Playwright becomes an ops burden.
3. **Tradeoffs**
   - Running headless browsers is resource-heavy and must be sandboxed (security) and
     queued (it's slow) — hence it lives in the worker tier, not the web request path.
4. **Future scalability**
   - Scale via a dedicated worker pool or a hosted browser service; isolation and
     human-confirmation policies from the security architecture apply.

> Not in the budget for Phases 0–5; listed here so the architecture is decided in
> advance. No cost until Phase 7.

---

## 11. File Storage

**Decision: Supabase Storage (S3-compatible) early; keep an S3-compatible interface.**

1. **Why selected**
   - Stores uploaded documents and media; integrates with our Postgres/Auth/RLS stack and
     the free tier fits the budget.
   - S3-compatible API means no lock-in at the interface level.
2. **Alternatives considered**
   - **AWS S3:** the gold standard and strong resume signal, but more setup and a billing
     account to manage early; the natural migration target later.
   - **Cloudflare R2:** S3-compatible with **no egress fees** — a compelling, cheap
     option we may adopt as media volume grows.
3. **Tradeoffs**
   - Supabase Storage limits on the free tier; mitigated by the S3-compatible boundary
     making migration trivial.
4. **Future scalability**
   - Move to **Cloudflare R2** (egress-friendly) or **AWS S3** with a CDN as media scales
     — a config change, not a redesign.

---

## 12. Deployment

**Decision: Vercel (frontend) + Render/Railway or Fly.io (backend + workers) + Supabase
(DB/Auth/Storage). Docker for the backend.**

1. **Why selected**
   - **Vercel** is the zero-config home for Next.js with a free tier and edge CDN.
   - **Render / Railway / Fly.io** host the FastAPI service and background workers cheaply
     (free/hobby tiers ~$0–7/mo), with Docker for portability.
   - This trio keeps total fixed infra near **₹0–₹500/month**, leaving the budget for LLM
     calls.
   - **Docker** is essential resume value and guarantees we can move hosts anytime.
2. **Alternatives considered**
   - **AWS/GCP/Azure from day one:** maximum power and resume weight, but heavy ops and
     surprise-bill risk for a solo dev — premature.
   - **Single VPS (Hetzner/DigitalOcean droplet):** cheapest at scale and great learning,
     but you own all ops (security patches, uptime) — a viable later consolidation.
   - **Kubernetes:** explicitly rejected this early — operational overkill.
3. **Tradeoffs**
   - PaaS free tiers cold-start and have limits; acceptable for personal/early use.
   - Some platform lock-in; contained by Docker + S3-compatible storage + portable
     Postgres.
4. **Future scalability**
   - Graduate the backend to a VPS cluster or managed cloud (ECS/Cloud Run) when traffic
     justifies it; containers make the move low-risk.

---

## 13. Monitoring

**Decision: Sentry (errors) + structured logging now; add LLM-specific observability
(Langfuse) for agent tracing.**

1. **Why selected**
   - **Sentry** (free tier) catches frontend + backend errors with great DX.
   - **Langfuse** (open-source, self-hostable or free tier) provides **LLM/agent-specific
     tracing**: prompt/response capture, token/cost tracking per agent run, and eval
     hooks — directly implementing the observability track in the system design and a
     standout AI-engineering skill.
   - Structured JSON logging from FastAPI ties it together.
2. **Alternatives considered**
   - **Datadog / New Relic:** powerful, but expensive and overkill for the budget.
   - **LangSmith:** excellent LLM tracing and resume-relevant, but tied to LangChain's
     orbit and paid; Langfuse is more neutral and self-hostable.
   - **Plain logs only:** cheapest, but you can't see *why* an agent did something — a
     dealbreaker for debugging agentic systems.
3. **Tradeoffs**
   - Another service (Langfuse) to run if self-hosted; free/hosted tier avoids that
     early.
4. **Future scalability**
   - Per-agent cost/latency dashboards and evals become the backbone of quality and unit
     economics as usage grows; add tracing (OpenTelemetry) when multi-service.

---

## 14. Analytics

**Decision: PostHog (product analytics + feature flags), self-host or free cloud tier.**

1. **Why selected**
   - One tool for product analytics, session insight, and **feature flags** — the latter
     lets a solo dev ship safely and gate phased agent rollouts.
   - Generous free tier; open-source and self-hostable, so it can fit the budget.
   - Privacy-friendly configuration aligns with the product's privacy-first philosophy.
2. **Alternatives considered**
   - **Google Analytics:** free and familiar, but weak for product (event) analytics and
     privacy-questionable for a user-data product.
   - **Mixpanel / Amplitude:** strong product analytics, but pricier as you grow and no
     feature flags in one package.
   - **Plausible/Umami:** lovely lightweight web analytics, but not product-grade event
     analytics.
3. **Tradeoffs**
   - PostHog can be heavy if self-hosted; use the free cloud tier early.
4. **Future scalability**
   - Scales into funnels, cohorts, A/B tests, and flag-gated SaaS rollouts — exactly what
     the public launch (Phase 14) needs.

---

## 15. Development Workflow

**Decision: Git + GitHub, GitHub Actions CI, monorepo, `uv`/`poetry` (Python) + `pnpm`
(JS), Ruff + Black + ESLint/Prettier, pytest + Playwright tests, Docker for parity.**

1. **Why selected**
   - **GitHub + Actions:** universal, free for this scale, and the expected professional
     baseline; CI runs lint/tests on every push.
   - **Monorepo** (`frontend/`, `backend/`, `docs/`, `architecture/`): one place, shared
     conventions, atomic changes — ideal for a solo dev (matches the existing structure).
   - **Tooling:** Ruff/Black (Python) and ESLint/Prettier (JS) enforce consistency for
     free; **pytest** for backend, Playwright for E2E; **Docker** for local↔prod parity.
   - **Conventional commits + a `CHANGELOG`** instill startup-grade discipline solo.
2. **Alternatives considered**
   - **GitLab CI / CircleCI:** capable, but GitHub is the default and best for resume
     visibility.
   - **Polyrepo:** cleaner service boundaries, but more overhead than a solo dev needs
     now.
   - **Nx/Turborepo:** great monorepo tooling, but added complexity unjustified at this
     size — adopt later if the JS side grows.
3. **Tradeoffs**
   - Some CI/tooling setup time upfront; pays back immediately in reliability and is
     itself resume-relevant.
4. **Future scalability**
   - Add release automation, preview deployments, and (if needed) Turborepo as the
     codebase and contributors grow.

---

# FINAL LOCKED STACK

> **Locked for Phases 0–5.** Optimized for a **solo developer**, **resume value**, **AI
> engineering relevance**, **SaaS scalability**, and a **₹1,000–₹2,000/month** budget
> (with that budget reserved primarily for LLM calls, not infrastructure).

| Layer | Locked Choice | Migration target at scale |
| --- | --- | --- |
| **Frontend** | Next.js (React, TypeScript) + Tailwind + shadcn/ui | (same) → React Native for mobile |
| **Backend** | Python + FastAPI (async) | Horizontal scale + worker tier |
| **Database** | PostgreSQL via Supabase | Managed Postgres (Neon/RDS/Cloud SQL) |
| **Vector DB** | pgvector (in Postgres) | Qdrant |
| **Authentication** | Supabase Auth + Postgres RLS | Clerk/Auth0/Cognito if needed |
| **Memory Layer** | Custom service on Postgres + pgvector | + caching / graph / Qdrant internally |
| **AI Models** | Claude (Haiku + Sonnet/Opus) via a provider-abstracted gateway | Multi-provider cost routing; local models for cheap tasks |
| **Agent Framework** | Custom orchestration on the Anthropic SDK | Adopt LangGraph per-workflow if warranted |
| **Search Layer** | pgvector + Postgres full-text (internal); Tavily/Brave (web) | Meilisearch/Typesense/OpenSearch |
| **Browser Automation** | Playwright (Phase 7; planned now) | Worker pool / hosted browser (Browserbase) |
| **File Storage** | Supabase Storage (S3-compatible) | Cloudflare R2 / AWS S3 + CDN |
| **Deployment** | Vercel (FE) + Render/Railway/Fly.io (BE+workers) + Docker | VPS cluster / Cloud Run / ECS |
| **Monitoring** | Sentry + Langfuse (LLM tracing) + structured logs | + OpenTelemetry, per-agent dashboards |
| **Analytics** | PostHog (analytics + feature flags) | Funnels/cohorts/A-B at SaaS scale |
| **Dev Workflow** | GitHub + Actions CI, monorepo, Ruff/Black + ESLint/Prettier, pytest + Playwright, Docker | + release automation, Turborepo |

### Estimated Monthly Cost (Phases 0–5)

| Category | Expected cost |
| --- | --- |
| Hosting (Vercel + Render/Railway free/hobby tiers) | ₹0 – ₹500 |
| Database / Auth / Storage (Supabase free tier) | ₹0 |
| Monitoring / Analytics (Sentry + Langfuse + PostHog free tiers) | ₹0 |
| **LLM API usage (Claude — the real variable cost)** | **₹800 – ₹1,500** |
| Web search API (Tavily, Phase 4+, low volume) | ₹0 – ₹200 |
| **Total** | **≈ ₹1,000 – ₹2,000 / month** ✅ |

### Why this stack wins on each priority

- 🎓 **Fast learning:** one DB (Postgres does relational + vector + search), managed
  Auth/Storage, PaaS deploys — minimal moving parts for one person.
- 💼 **Resume value:** Next.js + TypeScript, FastAPI, PostgreSQL, Docker, GitHub Actions,
  Playwright — the modern, hireable baseline.
- 🤖 **AI engineering relevance:** custom memory + agent orchestration on the Anthropic
  SDK, pgvector RAG, hybrid search, and Langfuse LLM observability — the exact skills the
  AI job market rewards.
- 📈 **SaaS scalability:** multi-tenant Postgres + RLS, stateless services + workers, and
  clean abstractions (Memory Service, LLM gateway, S3 interface) so every component has a
  no-rewrite migration path.
- 💰 **Low cost:** free tiers cover infrastructure; the budget is deliberately reserved
  for model calls, with tiering + prompt caching + memory-driven context trimming keeping
  LLM spend inside ₹1,000–₹2,000.

---

_This stack realizes [system-design.md](system-design.md) and the plan in
[../docs/ROADMAP.md](../docs/ROADMAP.md). Re-evaluate at the Phase 6 boundary or the first
paying customer._
