# GUMMY OS — Product Overview

> What GUMMY OS *is* from a product and user perspective, at the M8.5 freeze
> point. For the engineering view see `GUMMY_OS_ARCHITECTURE.md`.

---

## 1. One sentence

**GUMMY OS is a personal, memory-first AI operating system** — an assistant named
**Gummy** that learns you over time and routes your requests to a team of
specialized agents (career, learning, planning, memory, research), all grounded in
a private, consent-based long-term memory.

---

## 2. Who it's for

- **Today (personal):** a single power user — the founder — using Gummy for career
  growth, learning, research, planning, and document intelligence.
- **By design (future):** multi-tenant SaaS for individuals, then teams and
  organizations, with the same memory + agent substrate.

---

## 3. The core promise

> *An assistant that remembers you, gets more useful the longer you use it, and
> grows from one helper into a coordinated team — while keeping your data private
> and under your control.*

Three product pillars:

1. **Memory that compounds.** Every conversation contributes durable, categorized
   memory. Gummy recalls what matters across sessions — and you can see, edit, and
   delete what it knows.
2. **A team, not a chatbot.** Requests are routed to the right specialist
   automatically (or you pick one), each grounded in your knowledge.
3. **Consent and control.** Memory is earned, not assumed; provenance is tracked;
   isolation is enforced at the database layer.

---

## 4. What a user can do today

| Capability | What it feels like |
| --- | --- |
| **Chat workspace** | Streaming conversations with Gummy; pick Auto or a specific agent; see which agent answered and what memory was used |
| **Memory Center** | Browse, search, filter, edit, archive, and delete everything Gummy remembers — with source tracking |
| **Goals** | Create goals, milestones, and tasks; Gummy can detect goals from chat and track progress |
| **Files** | Upload PDFs/DOCX/TXT/MD/CSV/XLSX; ask questions about them ("what's in my resume?"); attach a file to a message for focused analysis |
| **Unified search** | Search across conversations, messages, and memories from any screen |
| **Specialist agents** | Career, Learning, Planner, Memory, Research — each tuned to its domain |
| **Profile & settings** | Display name, timezone, language; account info; recent activity |
| **Dashboard** | Understanding score, recent files, and activity snapshot |

---

## 5. The agent workforce

| Agent | Helps with |
| --- | --- |
| **Career** | Resumes, internships, job applications, LinkedIn, salary, interview prep |
| **Learning** | Explaining topics, study roadmaps, curricula, structured learning paths |
| **Planner** | Goals, milestones, timelines, schedules, step-by-step plans |
| **Memory** | "What do you know about me" — profile and history summaries |
| **Research** | Compare options, analyze markets/trends, synthesize findings (live web search arriving) |
| **General** | Anything else — the conversational catch-all |

You let Gummy **route automatically** based on what you ask, or **pin an agent**
from the workspace selector. A diagnostics view can explain *why* a query routed
where it did.

---

## 6. What makes it different

- **Memory-first, not memory-bolted-on.** The whole system is built around a
  durable, per-user memory spine — every feature reads from and writes to it.
- **Private by construction.** Fail-closed database-level tenant isolation means
  one user's data can't leak into another's, even through an application bug.
- **Grounded answers.** Agents answer from *your* memories, goals, and documents —
  not just generic model knowledge — through a single unified knowledge layer.
- **Honest UI.** Only working functionality is shown; placeholder controls were
  deliberately removed. What you see, works.

---

## 7. Maturity & boundaries (honest)

**Shipped and working:** memory engine, auth/security, conversation engine, goals,
file intelligence (keyword RAG), unified knowledge layer, five-specialist routed
workforce, streaming web client, observability.

**Seam-only / not yet live at the freeze:**
- **Live web search** — Tavily is wired into the provider seam and verified (off
  by default).
- **Vector file RAG** — file retrieval is keyword-based; semantic ranking is the
  next layer.
- **Automation & actions** — Gummy answers and proposes; it does not yet *act*
  (no scheduling, no external actions). The approval/permission scaffolding exists
  for when it does.
- **Voice / automation surfaces** in the UI are placeholders for planned phases.

---

## 8. Where the product goes next

The substrate (memory + conversation + knowledge + agents) is built. The roadmap
layers *intelligence* then *action* on top:

- **M9 Workflow Learning** — recognize recurring routines (daily study, job
  search, interview prep).
- **M10 Automation Engine** — execute those routines (reminders, reviews, summaries).
- **M11 Multi-Agent Collaboration** — specialists working together on one task.
- **Phase 5 Action Layer** — Gummy performs actions (browser, tools, applications)
  under human-in-the-loop approvals.

See `FUTURE_ROADMAP.md` for the full path through Phase 9.

---

## 9. The vision in one line

> From "an assistant that forgets" to a **personal AI operating system** — and
> eventually a platform — that remembers you, reasons with a team, and acts on
> your behalf, safely.
