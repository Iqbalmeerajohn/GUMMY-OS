# GUMMY OS — Features

This document catalogues GUMMY OS capabilities across three horizons — **Current**,
**Planned**, and **Future** — followed by a description of every agent in the system.

> Status reflects the Phase 0 starting point: the foundation is being laid, and most
> capabilities are planned. See [ROADMAP.md](ROADMAP.md) for sequencing.

---

## 1. Current Features (Phase 0)

These exist *today* as part of the foundation.

- **Professional project structure** — clean separation of frontend, backend, docs,
  and architecture.
- **Product documentation** — Vision, Roadmap, and this Features catalogue.
- **Architecture documentation** — system design and database design.
- **Defined data model** — the core schema (users, conversations, messages, memories,
  documents, jobs, research_reports, settings).
- **Defined agent architecture** — orchestrator + specialized agents pattern.

> No application code yet — intentionally. Phase 0 is foundation only.

---

## 2. Planned Features (Phases 1–7)

Committed and scoped; built in dependency order.

### Memory & Knowledge (Phase 1)
- Persistent long-term memory across all sessions and agents.
- Semantic recall via embeddings + vector search.
- Conversation history with summarization/compaction.
- Document ingestion: upload, parse, chunk, embed, and search any document.

### Career (Phase 2)
- Resume understanding and per-role tailoring.
- Job discovery, tracking, and pipeline management.
- Auto-drafted applications, cover letters, and outreach.
- Interview preparation grounded in personal memory.

### Learning (Phase 3)
- Personalized curricula and study plans.
- Spaced-repetition review and progress tracking.
- Learning derived from your own documents and research.

### Research (Phase 4)
- Multi-step, structured research with synthesis.
- Source evaluation and citation.
- Reusable, stored research reports.

### Building (Phase 5)
- Project planning and scaffolding.
- Context-aware code generation from memory + research.

### Daily Life (Phase 6)
- Tasks, reminders, scheduling, and routines.
- Calendar and email assistance.
- Proactive, goal-aware nudges.

### Web Action (Phase 7)
- Automated browsing, extraction, and form completion.
- Safe, sandboxed, confirmable web actions.

---

## 3. Future Features (Phases 8–14)

Directionally committed; design to follow.

- **Personality Layer** — a unified, tunable JARVIS-like identity across all agents.
- **Vision** — image understanding, OCR, and screenshot reasoning.
- **Video** — video understanding, transcription, summarization, and creation.
- **Social Media** — content drafting, scheduling, and engagement management.
- **Voice** — full hands-free, real-time conversational voice interface.
- **Mobile** — native/cross-platform app with proactive push.
- **Business Automation** — multi-user orgs, shared memory, business agents,
  workflow automation, and an extensible agent marketplace.

---

## 4. Agent Descriptions

GUMMY OS is built around an **Orchestrator** that routes intent to **specialized
agents**. Each agent owns a domain, has access to shared long-term memory, and can both
*advise* and *act*.

### 🧭 Orchestrator (Core)
The conductor. Interprets user intent, decides which agent(s) should handle a request,
routes context, composes multi-agent results, and maintains coherence. Always present;
not a "phase" but the backbone.

### 🧠 Memory System (Core — Phase 1)
Not a user-facing agent but the substrate every agent depends on. Captures, stores,
summarizes, and recalls knowledge — short-term conversation context and long-term
semantic memory. The single most important component.

### 💼 Career Agent (Phase 2)
Owns the job-search and career-growth loop: resume tailoring, job discovery and
tracking, application/cover-letter/outreach drafting, and interview prep.

### 📚 Learning Agent (Phase 3)
A personalized tutor: builds curricula, schedules spaced repetition, tracks progress,
and turns your documents and research into structured learning.

### 🔬 Research Agent (Phase 4)
A deep-research analyst: plans multi-step investigations, gathers and evaluates
sources, synthesizes findings, and produces citeable, reusable research reports.

### 🛠️ Builder Agent (Phase 5)
A technical co-builder: plans projects, scaffolds, and generates code using research
and long-term memory as context.

### 🗓️ Daily Life Agent (Phase 6)
The operations manager for daily life: tasks, reminders, scheduling, calendar/email,
and proactive nudges aligned to your goals.

### 🌐 Browser Agent (Phase 7)
The system's hands on the web: automated browsing, data extraction, and safe,
confirmable web actions that empower Research and Career.

### 🎭 Personality Layer (Phase 8)
A cross-cutting identity that gives every agent a consistent, tunable voice and
behavior — the "feel" of a single coherent assistant.

### 👁️ Vision Agent (Phase 9)
Understands visual input: images, screenshots, and visual documents, feeding
multimodal context into memory and other agents.

### 🎬 Video Agent (Phase 10)
Understands and generates video: transcription, summarization, segment indexing, and
content creation.

### 📣 Social Media Agent (Phase 11)
Manages social presence: drafting, scheduling, cross-posting, and engagement —
powered by the Personality, Vision, and Video agents.

### 🎙️ Voice Assistant (Phase 12)
The JARVIS interface: real-time speech in/out for hands-free interaction.

### 📱 Mobile App (Phase 13)
GUMMY OS on the go: chat, voice, and vision with proactive notifications.

### 🏢 Business Automation Layer (Phase 14)
The platform tier: org-level shared memory, business-domain agents, workflow
automation, and an extensible agent ecosystem.

---

_For how agents are implemented and coordinated, see
[../architecture/system-design.md](../architecture/system-design.md)._
