# The GUMMY OS Story

> A product history — how a single-founder project went from a rebrand and a
> blank backend to a routed multi-agent AI operating system with a memory spine,
> verified by ~600 automated tests, across nine delivery milestones. Written at
> the M8.5 development-freeze point (2026-06-24).

---

## The premise

Mainstream AI assistants are **stateless and forgetful**. They answer a question
and lose all context — they don't remember you across sessions, can't safely
isolate one person's data from another's at the database layer, and offer no
structured path from "things you said in chat" to "durable knowledge the
assistant acts on."

GUMMY OS was started to answer a different question: *what if the assistant
remembered you, got more useful the longer you used it, and could grow from a
single helper into a coordinated team of specialists — without ever leaking one
user's life into another's?*

The assistant is named **Gummy**. The project is built **first for personal use**
(career, learning, research, planning) with a deliberate, designed-in path toward
a multi-tenant SaaS platform.

---

## The throughline: memory first

Every architectural decision flows from one commitment: **memory is the spine,
not a feature.** Each conversation both *reads from* and *contributes to* a
durable, per-user long-term memory, behind strict tenant isolation. The system
becomes more valuable with use while staying private and safe to run as
multi-tenant SaaS. Everything built later — goals, files, knowledge, agents —
plugs into that one memory substrate rather than forking its own store.

The second commitment is **consent**: "memory is earned, not assumed." Automatic
extraction is gated by a consent mode; the default persists nothing silently, and
every durable memory records where it came from.

---

## The journey, phase by phase

### Phase 0 — Foundation & Rebranding *(complete)*
IQBAL OS became **GUMMY OS**. Before a line of application code: vision, the
design system, technical conventions, the architecture specs, ADRs (tech stack,
memory-first, PostgreSQL/pgvector, FastAPI), and the repository structure. The
discipline of a startup engineering org applied to a solo project.

### Phase 1 — Memory Engine *(complete)*
The spine. Structured, categorized memories (profile, preference, career,
learning, project, conversation, document) with importance + confidence scoring;
**semantic recall** via pgvector cosine search; **hybrid ranking** blending
similarity, importance, recency, and confidence; immutable **versioning** and
**reinforcement** (recall makes a memory stickier). A background embedding worker
keeps vectors fresh off the request path.

### Phase 1.5 — Authentication & Security *(complete)*
Security as architecture, not an afterthought. Supabase **JWT** verified at the
edge; a per-request **tenant context**; and the centerpiece: **fail-closed
Postgres Row-Level Security** on every tenant table, keyed on a per-transaction
GUC, enforced under a dedicated non-bypass database role. If the tenant is unset,
queries return zero rows — isolation can't be undone by an application bug.

### Phase 2 — Conversation Engine *(complete)*
Persistent, resume-anywhere threads. The **memory-aware turn**: every reply is
grounded in recent history + a rolling summary + retrieved long-term memories,
assembled within a token budget. **Rolling summaries** (versioned + embedded)
keep long threads cheap. **Conversation → memory extraction** distills durable
facts through the existing Memory Engine — consent-gated, provenance-linked, and
**watermark-first** so failures retry and successes never duplicate. Plus hybrid
**conversation search** (full-text + semantic).

### Phase 3 — Core Intelligence Layer *(complete)*
The product became usable and capable.
- **M4** turned the backend into a polished product: a streaming chat workspace,
  a first-class Memory Center, full conversation management, and unified search.
- **M5 / M5.5 — Goals & Goal Intelligence:** goals, milestones, tasks, progress,
  and conversational goal extraction; agents can read active goals.
- **M6 / M6.5 — Files & File Intelligence:** upload → extract → chunk → retrieve,
  then file-aware chat (keyword RAG) and chat attachments. Files became
  answerable knowledge, not just blobs.

### Phase 4 — Knowledge & Agent Workforce *(partially complete — the freeze point)*
- **M7 — Unified Knowledge & Retrieval Engine:** one seam that ranks and
  compresses everything Gummy knows (memories, conversation summaries, goals,
  files) into a single grounded context pack. The **single-retrieval-layer rule**
  was born here: agents never retrieve on their own.
- **M8 — Multi-Agent Workforce:** Gummy became a *team*. A deterministic Agent
  Router selects one of five specialists — **Career, Learning, Planner, Memory,
  Research** — or falls back to General, all grounded only through the M7 seam.
  Users let the Router decide (Auto) or pin an agent. Full A2A audit trail,
  Langfuse tracing, PostHog analytics, and a diagnostics endpoint that explains
  routing.
- **M8 Polish + M8.5 — Search Layer:** hardened routing and added the
  `SearchProvider` seam with eligibility gating — the clean insertion point for
  Brave/Tavily live web search, shipped as a seam (not yet wired). **This is the
  freeze point.**

---

## Turning points (the hard problems)

These are the moments the project's character was forged — each one is a real
engineering challenge solved, not a tutorial step.

1. **Fail-closed multi-tenant isolation at the database layer.** During a live
   apply, table grants weren't propagating to migration-created tables — a
   production-class security gap. The fix: make every migration ship the table's
   *full* access policy (RLS **and** grants), so security travels with the schema.

2. **Deterministic message ordering.** `created_at` is fixed per Postgres
   transaction (and second-resolution on SQLite), so messages appended together
   couldn't be ordered. A monotonic per-conversation sequence
   (`UNIQUE(conversation_id, seq)`) became the insertion-faithful sort key.

3. **Chat → memory without duplicating the engine.** Every extracted fact routes
   through the existing memory service (reusing scoring, versioning, embedding),
   adding only provenance — consent-gated and watermark-first so the unit of work
   rolls back on LLM failure and never re-extracts on success.

4. **Enrichment off the request path.** Title generation, summarization, and
   extraction run post-commit on an async worker, each consumer in its own
   session — the user's turn stays instant and one failing consumer never crashes
   the worker.

5. **One retrieval layer for many agents (M7).** Rather than let each new agent
   grow its own retrieval (and its own bugs and cost), all grounding flows through
   a single ranked, compressed knowledge seam — so five specialists shipped in M8
   without five retrieval implementations.

6. **Routing that never fails a request (M8).** Deterministic, free keyword
   scoring with graceful degradation to General, a guaranteed orchestrator
   fallback to the grounded reply, and per-run step/cost caps — so the team of
   agents is as reliable as the single assistant was.

---

## Where it stands

At the freeze point GUMMY OS is a working, tested, multi-agent AI backend with a
polished web client: a memory spine, a consent-based conversation engine, goals,
file intelligence, a unified knowledge layer, and a routed five-specialist
workforce — **598 passing tests**, 21 migrations, fail-closed RLS proven live.

The founder is pausing active development to focus on career milestones (resume,
interviews, exams). The project is being **preserved, documented, and
roadmapped** — not abandoned. The next chapters (Workflow Learning, Automation,
Multi-Agent Collaboration, and the Action layer) are designed and waiting.

> _The arc so far: from "an assistant that forgets" to "an operating system that
> remembers, reasons with a team, and is safe to share." The substrate is built.
> The workforce has started. The execution layer is next._
