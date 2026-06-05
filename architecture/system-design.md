# GUMMY OS — System Design

This document describes the technical architecture of GUMMY OS: how the system is
structured, how agents are coordinated, how memory works, how the system is secured,
and how data and users move through it.

> **Scope:** Architecture and design only (Phase 0). No implementation. Technology
> choices below are *recommended defaults* chosen for scalability and a smooth path to
> SaaS — they are not yet locked.

---

## 1. Architectural Principles

1. **Memory-centric.** A shared long-term memory is the gravitational center; every
   agent reads from and writes to it.
2. **Agent-oriented.** Capabilities are specialized agents behind a single
   orchestrator, not one monolithic prompt.
3. **Multi-tenant from day one.** Every record is scoped to a `user` (and later an
   `organization`) so the jump from personal to SaaS is an evolution, not a rewrite.
4. **Stateless services, stateful stores.** Application services scale horizontally;
   all state lives in databases, vector stores, caches, and object storage.
5. **Action with guardrails.** Agents can act, but high-impact actions are
   logged, reversible where possible, and human-confirmable.
6. **Observable & evaluable.** Every agent run is traced, costed, and measurable.

---

## 2. High-Level Architecture

A layered architecture from client to data:

```
┌──────────────────────────────────────────────────────────────────────┐
│                            CLIENTS                                      │
│   Web App (frontend/)   ·   Mobile (Phase 13)   ·   Voice (Phase 12)   │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │ HTTPS / WSS (REST + streaming)
┌───────────────────────────────▼──────────────────────────────────────┐
│                          API GATEWAY                                    │
│   AuthN/AuthZ · rate limiting · request routing · validation           │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │
┌───────────────────────────────▼──────────────────────────────────────┐
│                       APPLICATION / BACKEND (backend/)                  │
│                                                                        │
│   ┌──────────────────────────────────────────────────────────────┐   │
│   │                      ORCHESTRATOR                              │   │
│   │   intent parsing · agent routing · context assembly ·         │   │
│   │   multi-agent composition · response streaming                │   │
│   └───────────────┬──────────────────────────┬────────────────────┘  │
│                   │                          │                        │
│   ┌───────────────▼───────────┐   ┌──────────▼────────────────────┐  │
│   │      AGENT RUNTIME         │   │       MEMORY SERVICE          │  │
│   │  Career · Learning ·       │◀─▶│  capture · retrieve ·         │  │
│   │  Research · Builder ·      │   │  summarize · embed · recall   │  │
│   │  Daily Life · Browser ...  │   └──────────┬────────────────────┘ │
│   └───────────────┬───────────┘              │                       │
│                   │                          │                       │
│   ┌───────────────▼──────────────────────────▼────────────────────┐ │
│   │     SHARED SERVICES: LLM gateway · tools · queue/workers ·     │ │
│   │     embeddings · file ingestion · integrations (email/cal/web) │ │
│   └────────────────────────────────────────────────────────────────┘│
└───────────────────────────────┬──────────────────────────────────────┘
                                 │
┌───────────────────────────────▼──────────────────────────────────────┐
│                            DATA LAYER                                   │
│  Relational DB (Postgres)  ·  Vector Store (pgvector/dedicated)         │
│  Object Storage (files)    ·  Cache/Queue (Redis)                       │
└───────────────────────────────────────────────────────────────────────┘
```

### Recommended Default Stack
- **Frontend:** React/Next.js (web), React Native (mobile, Phase 13).
- **Backend:** Python (FastAPI) or Node (NestJS) — async-friendly for agent/LLM I/O.
- **LLM:** Claude (Anthropic) as the primary model family via a provider-abstracted
  LLM gateway, so models are swappable per-agent and per-task.
- **Relational DB:** PostgreSQL.
- **Vector store:** `pgvector` to start (one fewer system), graduating to a dedicated
  vector DB at scale.
- **Cache/Queue:** Redis (+ a worker framework for async/background jobs).
- **Object storage:** S3-compatible storage for documents and media.

---

## 3. Agent Architecture

### 3.1 The Orchestrator + Specialist pattern
A central **Orchestrator** is the single entry point for user intent. It:

1. **Parses intent** from the user message + conversation + relevant memory.
2. **Plans** which agent(s) are needed (single-agent or a multi-agent workflow).
3. **Assembles context** by querying the Memory Service for relevant memories,
   documents, and history.
4. **Dispatches** to one or more specialized agents.
5. **Composes** their outputs into a single coherent response.
6. **Persists** new messages and memory writes.

### 3.2 Anatomy of an Agent
Every specialized agent shares a common contract:

| Component | Responsibility |
| --- | --- |
| **Role/Prompt** | Domain expertise and behavior definition. |
| **Tools** | Functions the agent may call (search, web, file, DB, integrations). |
| **Memory access** | Scoped read/write to the shared Memory Service. |
| **Input/Output schema** | Typed contract so agents are composable. |
| **Policies** | Permissions, confirmation rules, cost/usage limits. |

Because agents share one contract, **adding an agent is a pluggable operation** — the
foundation for the Phase 14 agent ecosystem.

### 3.3 Coordination patterns
- **Single-agent:** simple requests routed to one specialist.
- **Pipeline:** output of one agent feeds the next (e.g. Research → Learning).
- **Parallel fan-out / gather:** multiple agents work concurrently; orchestrator merges.
- **Human-in-the-loop:** agent proposes; user confirms before high-impact action.

---

## 4. Memory Architecture

Memory is the moat. It is organized into tiers:

### 4.1 Short-Term (Working) Memory
- The active conversation: recent `messages` in a `conversation`.
- Kept in the model context window; summarized/compacted as it grows.

### 4.2 Long-Term (Persistent) Memory
- **Episodic** — what happened (conversations, decisions, events).
- **Semantic** — durable facts, preferences, and knowledge (`memories` table).
- **Document** — ingested files, chunked and embedded (`documents` + chunks).

### 4.3 The Memory Pipeline
```
Capture        →  Process            →  Store               →  Recall
─────────────     ────────────────      ──────────────────     ────────────────
new message /     extract facts,        write rows +           semantic search
document /        summarize, chunk,     embeddings to          (vector) + filters
agent output      embed                 Postgres + vector      → ranked context
```

- **Capture:** conversations, documents, and agent outputs are candidates for memory.
- **Process:** salient facts/summaries are extracted; text is chunked and embedded.
- **Store:** structured rows in Postgres; vectors in the vector store; files in object
  storage. Everything `user`-scoped.
- **Recall:** on each request, the Memory Service runs hybrid retrieval (vector
  similarity + metadata filters + recency) to assemble the most relevant context.

### 4.4 Compaction & hygiene
- Long conversations are summarized into compact memories to control context size/cost.
- Memories carry importance/confidence so the system can prioritize and forget noise.

---

## 5. Security Architecture

Security is a cross-cutting track, hardened **before** SaaS launch.

### 5.1 Tenancy & isolation
- Every row is scoped by `user_id` (and `organization_id` in Phase 14).
- Application-level scoping today; **row-level security (RLS)** in Postgres as
  defense-in-depth for multi-tenant SaaS.

### 5.2 Authentication & authorization
- Token-based auth (JWT/session) at the API Gateway.
- Role/permission model; per-agent tool permissions and action policies.

### 5.3 Data protection
- TLS in transit; encryption at rest for DB, vector store, and object storage.
- Secrets in a dedicated secret manager — never in code or the repo.
- Sensitive fields (tokens, credentials) encrypted at the field level.

### 5.4 Agent & action safety
- Tool calls are validated and permission-checked.
- High-impact actions (sending email, web actions, deletions) require confirmation
  and are recorded in an audit log.
- Sandboxed execution for the Browser/Builder agents.

### 5.5 Privacy & governance
- User owns their data: export and deletion supported by design.
- Full audit trail of agent actions for transparency and accountability.
- Per-user cost/usage limits to prevent runaway agent loops.

---

## 6. Data Flow

A typical request, end to end:

```
1. User sends a message (Web/Mobile/Voice).
2. API Gateway authenticates, rate-limits, and forwards.
3. Orchestrator loads the conversation + asks Memory Service for relevant context.
4. Orchestrator parses intent → selects agent(s).
5. Agent(s) run: call the LLM gateway, use tools, read/write memory.
6. (If high-impact) user is asked to confirm the proposed action.
7. Orchestrator composes the final response and streams it back.
8. New messages, memories, documents, and artifacts are persisted.
9. Background workers handle async work (ingestion, embedding, long research jobs).
10. Everything is traced, costed, and logged for observability.
```

---

## 7. User Flow

The lifecycle of a user in GUMMY OS:

```
Onboard        →  Personalize      →  Daily Use            →  Compounding Value
────────────      ───────────────     ──────────────────      ──────────────────
sign up,          set goals,          chat + agents act,      memory grows; agents
create user,      preferences;        documents ingested,     get sharper; system
init settings     seed initial        tasks/jobs/research     becomes indispensable
                  memory              tracked over time
```

1. **Onboarding** — account creation; a `user` and default `settings` are provisioned.
2. **Personalization** — the user states goals and preferences; initial `memories` are
   seeded; documents can be uploaded.
3. **Daily use** — the user interacts through conversations; the orchestrator routes to
   agents that act and persist results (`jobs`, `research_reports`, memories).
4. **Compounding value** — long-term memory accumulates, making every agent more
   personalized and capable over time. This is the retention and moat engine.

---

## 8. Scalability & Operations (cross-cutting)

- **Horizontal scale:** stateless services behind a load balancer; all state externalized.
- **Async by default:** queue + workers for ingestion, embedding, and long-running
  agent jobs so user-facing requests stay fast.
- **Caching:** Redis for hot context and rate limiting.
- **Observability:** structured logging, distributed tracing of agent runs, cost
  tracking per request/agent, and agent evaluations.
- **Cost control:** model selection per task, prompt/result caching, and per-user limits.

---

_See [database-design.md](database-design.md) for the concrete data model that backs
this architecture._
