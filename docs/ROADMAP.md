# GUMMY OS — Roadmap

This roadmap describes the phased evolution of GUMMY OS from an empty repository to a
full Personal & Business Multi-Agent AI Operating System.

**Philosophy:** Each phase ships something *usable*. We build the foundation and memory
first (because memory is the moat), then layer specialized agents one at a time, then
expand into multimodal and platform capabilities.

> Phases are sequenced by dependency, not locked to dates. A phase is "done" when it is
> stable, documented, and delivering real value to the primary user.

---

## Legend

| Status | Meaning |
| --- | --- |
| ✅ Done | Completed and stable |
| 🚧 In Progress | Actively being built |
| ⏳ Planned | Scoped, not started |
| 🔮 Future | Directionally committed, design pending |

---

## Phase 0 — Foundation 🚧

**Goal:** Establish a professional engineering foundation before any code.

- Repository structure (`frontend/`, `backend/`, `docs/`, `architecture/`).
- Product documentation: Vision, Roadmap, Features.
- Architecture documentation: system design, database design.
- Define core principles, data model, and agent architecture.
- Decide the canonical tech stack and conventions.

**Exit criteria:** A new contributor (or future me) can understand *what* we're building,
*why*, and *how* the system is shaped — without reading any code.

---

## Phase 1 — Memory System ⏳

**Goal:** Build the persistent long-term memory that every agent depends on.

- Core data model: users, conversations, messages, memories, documents.
- Short-term (conversation) memory + long-term (semantic) memory.
- Vector store + embeddings pipeline for semantic recall.
- Memory write path (capture), retrieval path (recall), and summarization/compaction.
- Document ingestion (upload → parse → chunk → embed → index).

**Why first:** Every agent is only as good as what it remembers. This is the moat.

---

## Phase 2 — Career Agent ⏳

**Goal:** Automate and elevate the job search and career growth loop.

- Resume/CV understanding and tailoring.
- Job discovery, tracking, and application drafting.
- Cover letters, outreach messages, interview prep from memory.
- `jobs` data model and pipeline tracking.

**Why now:** High, immediate, measurable personal value — a perfect first agent.

---

## Phase 3 — Learning Agent ⏳

**Goal:** A personalized tutor and knowledge-acquisition system.

- Skill/topic planning and curriculum generation.
- Spaced repetition and progress tracking.
- Learns from ingested documents and past conversations.
- Turns research outputs into structured learning.

---

## Phase 4 — Research Agent ⏳

**Goal:** Deep, structured research on demand.

- Multi-step research planning and synthesis.
- Source gathering, evaluation, and citation.
- Produces structured `research_reports` stored in memory.
- Feeds the Learning and Builder agents.

---

## Phase 5 — Builder Agent ⏳

**Goal:** An agent that helps design and build software and projects.

- Project scaffolding, technical planning, and code generation.
- Uses Research outputs and long-term memory for context.
- Integrates with the repo/workspace.

---

## Phase 6 — Daily Life Agent ⏳

**Goal:** Manage the operational layer of daily life.

- Tasks, reminders, scheduling, and routines.
- Calendar and email assistance.
- Proactive nudges based on goals and memory.

---

## Phase 7 — Browser Agent ⏳

**Goal:** Give agents the ability to act on the live web.

- Headless/automated browsing and form-filling.
- Web data extraction feeding Research and Career agents.
- Safe, sandboxed, human-confirmable web actions.

---

## Phase 8 — Personality Layer 🔮

**Goal:** A coherent, consistent identity across all agents.

- Unified tone, voice, and behavior (the "JARVIS feel").
- User-tunable personality and communication preferences.
- Persona consistency layered over every agent response.

---

## Phase 9 — Vision Agent 🔮

**Goal:** Understand images and visual input.

- Image understanding, OCR, screenshot reasoning.
- Visual document ingestion into memory.
- Feeds multimodal context to other agents.

---

## Phase 10 — Video Agent 🔮

**Goal:** Understand and generate video content.

- Video understanding, transcription, and summarization.
- Clip/segment extraction and indexing into memory.
- Foundation for content creation workflows.

---

## Phase 11 — Social Media Agent 🔮

**Goal:** Manage and grow social presence.

- Content drafting, scheduling, and cross-posting.
- Engagement monitoring and response drafting.
- Uses Personality + Vision + Video agents.

---

## Phase 12 — Voice Assistant 🔮

**Goal:** True hands-free, JARVIS-style interaction.

- Speech-to-text and text-to-speech pipeline.
- Real-time conversational voice interface.
- Wake-word / always-available mode.

---

## Phase 13 — Mobile App 🔮

**Goal:** GUMMY OS in your pocket.

- Native/cross-platform mobile client.
- Push notifications and proactive agent prompts.
- Voice + vision + chat on the go.

---

## Phase 14 — Business Automation Layer 🔮

**Goal:** Turn GUMMY OS into a platform for teams and businesses.

- Multi-user organizations with shared, permissioned memory.
- Business-domain agents (ops, sales, support, finance).
- Workflow automation, integrations, and an extensible agent marketplace.
- The bridge from "personal JARVIS" to "SaaS platform".

---

## Cross-Cutting Tracks (run across all phases)

- **Security & Privacy:** isolation, encryption, auditability — hardened before SaaS.
- **Observability:** logging, tracing, agent evaluation, cost tracking.
- **Scalability:** multi-tenancy and horizontal scale designed in from Phase 1.
- **Quality:** testing, evals, and human-in-the-loop safeguards.

---

_See [FEATURES.md](FEATURES.md) for the detailed feature catalogue and agent
descriptions, and [../architecture/system-design.md](../architecture/system-design.md)
for how these phases are realized technically._
