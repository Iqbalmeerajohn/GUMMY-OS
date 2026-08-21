# GUMMY OS — Future Roadmap

> The forward plan from the M8.5 freeze point through Phase 9. This is a
> **planning** document — nothing here is built. It preserves intent so work can
> resume cleanly after the development pause. Status legend: ✅ done · 🟡 partial ·
> ⏸ planned · 🔮 future.

---

## Status at the freeze

| Phase | Title | Status |
| --- | --- | --- |
| 0 | Foundation & Rebranding | ✅ |
| 1 | Memory Engine | ✅ |
| 1.5 | Authentication & Security | ✅ |
| 2 | Conversation Engine | ✅ |
| 3 | Core Intelligence (M4, M5/5.5, M6/6.5) | ✅ |
| **4** | **Knowledge & Agent Workforce** | 🟡 (M7, M8, M8.5 done; M9–M11 pending) |
| 5 | Action & Execution Layer | 🔮 |
| 6 | Personal AI Operating System | 🔮 |
| 7 | Platform & SaaS | 🔮 |
| 8 | Enterprise AI Workforce | 🔮 |
| 9 | GUMMY Ecosystem | 🔮 |

**Freeze line: end of M8.5.** Resume at M9.

---

## Phase 4 — remaining milestones

### M9 — Workflow Learning ⏸
**Purpose:** learn recurring user workflows.
**Examples:** daily study, daily job search, resume improvement, interview prep, AI
learning.
**Capabilities:** workflow discovery, pattern detection, workflow storage,
recommendations, optimization.
**Likely seams to build on:** the memory engine (store discovered workflows as a
new memory category), conversation history (pattern source), the knowledge ranker
(surface workflows as grounding). *No new retrieval layer — extend M7.*

### M10 — Automation Engine ⏸
**Purpose:** execute workflows automatically.
**Capabilities:** scheduling, recurring tasks, goal reviews, reminder systems,
automated summaries, internal workflow execution.
**Likely seams:** the existing async worker tier (move from in-process to a durable
queue here), goals/milestones for review triggers, the enrichment worker pattern
for scheduled summaries.

### M11 — Multi-Agent Collaboration ⏸
**Purpose:** multiple agents working together.
**Examples:** Career + Research, Career + Learning + Planner, Memory + Planner +
Research.
**Capabilities:** agent delegation, consultation, synthesis, multi-agent planning,
shared-context execution.
**Likely seams:** the orchestrator already supports `pipeline` and `parallel`
shapes and an A2A message trail — M11 is largely *richer plans + a synthesis
composer* on top of the existing runtime, not a new framework.

---

## Phase 5 — Action & Execution Layer 🔮

Move GUMMY from *answering* to *doing*.

- **M12 Browser Actions** — open sites, fill forms, navigate, perform tasks.
- **M13 Tool-Use Framework** — API execution, external services, connectors,
  orchestration.
- **M14 Action Agents** — Job Application, Research, Content, Business, Marketing,
  Execution agents.
- **M15 Human-in-the-Loop Approvals** — approval requests, safety checkpoints,
  review workflows, action confirmation.

**Already scaffolded for this:** `action_approvals` table, `policy_engine`,
`approval_service`, and the Green/Yellow/Red permission ceiling on every agent
manifest. The action choke point exists; Phase 5 wires real actions through it.

---

## Phase 6 — Personal AI Operating System 🔮

- **M16 Personal Workforce** — Career, Learning, Planner, Finance, Fitness,
  Research, Business agents running continuously.
- **M17 Personal Knowledge Graph** — relationship mapping, long-term reasoning, a
  life graph (evolution of the memory store).
- **M18 Predictive Intelligence** — anticipate needs, suggest actions, goal
  forecasting, opportunity detection.
- **M19 Life OS** — career, learning, planning, project management, decision support.

---

## Phase 7 — Platform & SaaS 🔮

- **M20 Multi-Tenant SaaS** — *the architecture is already multi-tenant and
  fail-closed; this is productization, billing, and onboarding, not a rewrite.*
- **M21 Team Workspaces** · **M22 Shared Memory** · **M23 Organization Agents** ·
  **M24 Workflow Marketplace** · **M25 Agent Marketplace**.

---

## Phase 8 — Enterprise AI Workforce 🔮

Enterprise memory, workflows, and agents; governance, compliance, observability,
audit trails. *The A2A audit trail and per-run accounting are early groundwork.*

---

## Phase 9 — GUMMY Ecosystem 🔮

Personal / Team / Enterprise AI OS, an Agent Marketplace, a Workflow Marketplace,
a Developer Platform, and an API Platform.

---

## Technical-debt backlog to clear before scaling (carry-over)

These are not new features — they are the cleanups that should happen alongside
M9–M11 / Phase 5 (full detail in `PROJECT_AUDIT.md §9`):

1. **Externalize the worker queue** (in-process → Redis/Celery) — do it as part of
   M10 Automation, which needs durable scheduling anyway.
2. ~~**Wire live web search**~~ — **done**: Tavily is wired into the search seam and live-verified. Remaining:
   natural companion to M9/Research.
3. **Vector file RAG** — swap a vector retriever under `file_context_service`.
4. **Move file processing off the request path** — reuse the worker pattern.
5. **Fix the conversation-search N+1** (batch the per-hit re-fetch).
6. **Add a Postgres CI stage** running the RLS-gated suite on every change.

---

## Recommended restart sequence (after the pause)

1. **Re-baseline** (½ day): run `pytest`, `ruff`, `mypy`; reconfirm green; skim
   this doc set and `GUMMY_OS_MASTER_DOCUMENT.md`.
2. **Wire live search** into the M8.5 seam — small, high-leverage, already designed.
3. **M9 Workflow Learning** — the planned next milestone; extend memory + knowledge,
   no new retrieval layer.
4. Then **M10 Automation** (bring the durable worker queue with it) → **M11
   Collaboration** (richer orchestrator plans + synthesis).

> The freeze is a clean checkpoint: substrate done, workforce started, execution
> layer designed and scaffolded. Resume at M9 with confidence.
