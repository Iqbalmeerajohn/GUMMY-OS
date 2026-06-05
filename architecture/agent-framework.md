# GUMMY OS — Agent Framework

This document defines the complete agent architecture of GUMMY OS: the **Master
Orchestrator**, the **Core Agents**, the **Future Agents**, and the rules that govern how
agents communicate, access tools, hold permissions, and live through a lifecycle —
including the path to LangGraph-based multi-agent orchestration.

> **Scope:** Architecture only (Phase 0). No implementation. Builds on
> [system-design.md](system-design.md), [memory-system.md](memory-system.md), and
> [security-system.md](security-system.md).

---

## 1. The Agent Model

GUMMY OS is a **multi-agent operating system**, not a single prompt. **Gummy** is the
persona the user experiences; underneath, a **Master Orchestrator** routes intent to
specialized agents that share one long-term memory and a common contract.

```
                                ┌─────────────────────────┐
            User  ───────────▶  │     MASTER ORCHESTRATOR  │  ◀── Personality Agent (voice)
                                │  intent · routing ·      │
                                │  context · composition   │
                                └────────────┬─────────────┘
                                             │ (typed tasks)
        ┌───────────────┬───────────────┬────┴────┬───────────────┬───────────────┐
        ▼               ▼               ▼         ▼               ▼               ▼
   Memory Agent    Career Agent   Learning Agent Research Agent Builder Agent  Daily Life Agent
        │               │               │         │               │               │
        └───────────────┴───────────────┴────┬────┴───────────────┴───────────────┘
                                             ▼
                                    Action Agent · Browser Agent
                                    Vision · Video · Social · Voice
                                             │
                          ┌──────────────────┴───────────────────┐
                          ▼                                       ▼
                   SHARED MEMORY (Memory Service)        TOOLS / INTEGRATIONS
                                                         (web, email, files, APIs)
```

---

## 2. Master Orchestrator

The conductor and single entry point for intent.

**Responsibilities**
1. **Intent parsing** — interpret the user request using the active conversation +
   recalled memory.
2. **Routing / planning** — decide which agent(s) handle it (single, pipeline, or
   parallel) and in what order.
3. **Context assembly** — query the Memory Service for relevant memories/documents/history
   and build a token-budgeted context pack.
4. **Delegation** — dispatch typed tasks to agents with least-privilege scopes.
5. **Composition** — merge agent outputs into one coherent Gummy response.
6. **Policy enforcement** — apply the Green/Yellow/Red permission model before any action.
7. **Persistence** — write messages, propose memories, log actions.

The Orchestrator is always present — the backbone, not a "phase."

---

## 3. Core Agents

Each core agent owns a domain, reads/writes shared memory, and has a declared permission
ceiling.

| Agent | Mission | Reads | Writes / Acts | Perm ceiling |
| --- | --- | --- | --- | --- |
| 🧠 **Memory Agent** | Capture, score, retrieve, summarize, version memory. | all memory | memory CRUD (consent-gated) | 🟡 Yellow |
| 💼 **Career Agent** | Job search, resume tailoring, applications, interview prep. | Career/Profile/Doc memory | drafts, `jobs`, applications | 🟡 Yellow |
| 📚 **Learning Agent** | Curricula, spaced repetition, skill tracking. | Learning/Doc memory | learning plans, progress | 🟡 Yellow |
| 🔬 **Research Agent** | Multi-step research, synthesis, citations. | memory + web | `research_reports` (drafts) | 🟢 Green (read) |
| 🛠️ **Builder Agent** | Plan & scaffold projects/code. | Project/Research memory | plans, code drafts, files | 🟡 Yellow |
| 🗓️ **Daily Life Agent** | Tasks, reminders, scheduling, calendar/email assist. | memory + integrations | tasks, drafts, schedules | 🟡 Yellow |
| ⚡ **Action Agent** | Execute approved external actions (the "hands"). | task + policy | email send, submit, post (gated) | 🔴 Red (gated) |
| 🌐 **Browser Agent** | Automated, sandboxed web actions & extraction. | task | navigate, fill, extract | 🟡 Yellow |
| 🎭 **Personality Agent** | Consistent voice/tone — the "Gummy feel". | prefs/personality | shapes all responses | 🟢 Green |
| 👁️ **Vision Agent** | Understand images, screenshots, visual docs. | media | extracted content → memory | 🟢 Green (read) |
| 🎬 **Video Agent** | Understand/transcribe/summarize/create video. | media | transcripts, clips | 🟡 Yellow |
| 📣 **Social Media Agent** | Draft, schedule, manage social presence. | Personality/Vision/Video | drafts → posting via Action Agent | 🔴 Red (post) |
| 🎙️ **Voice Agent** | Speech in/out; hands-free JARVIS interface. | audio | STT/TTS streams | 🟢 Green |

> **Action Agent is special:** other agents *propose* external actions; the Action Agent
> is the single, audited choke point that *executes* them — always under the
> Green/Yellow/Red policy (see [security-system.md](security-system.md)). This centralizes
> the riskiest capability behind one well-guarded door.

---

## 4. Future Agents

Designed for, but **not scheduled** into active phases (full concepts in
[../docs/FUTURE_AGENTS.md](../docs/FUTURE_AGENTS.md)):

- 📈 **Marketing Agent** — campaigns, content strategy, growth analytics.
- 💪 **Fitness Agent** — workouts, nutrition, health-goal tracking (sensitive → Red-heavy).
- (Plus exploratory: Finance, Travel, Shopping — see FUTURE_AGENTS.)

They plug into the same contract, so adding them is a pluggable operation — the foundation
for the Phase 14 agent ecosystem.

---

## 5. Agent Communication

Agents never free-form chat at each other. Communication is **structured and
orchestrated**:

- **Typed task contract** — the Orchestrator sends each agent a typed task
  `{intent, inputs, context_pack, permission_scope}` and receives a typed result
  `{output, proposed_actions, proposed_memories, citations, cost}`.
- **No peer-to-peer side channels** (early phases) — all coordination flows through the
  Orchestrator for traceability and safety. (Later, supervised sub-graphs may allow
  scoped agent-to-agent calls.)
- **Shared memory as the bus** — agents exchange durable knowledge via the Memory Service,
  not by passing giant payloads.

### Coordination patterns
- **Single-agent** — simple request → one specialist.
- **Pipeline** — e.g. Research → Learning, or Research → Builder.
- **Parallel fan-out / gather** — multiple agents run concurrently; Orchestrator merges.
- **Human-in-the-loop** — propose → confirm (Yellow/Red) → Action Agent executes.

---

## 6. Tool Access

- Each agent declares a **least-privilege tool manifest** (the only tools it may call).
- Tools are typed functions: web search, browser, file read/write, email, calendar,
  social APIs, payments, DB.
- **Tool calls pass through the policy engine** — the tier (Green/Yellow/Red) of the tool
  determines whether it runs, prompts, or blocks.
- External content fetched by tools is treated as **untrusted** (prompt-injection
  defense): it can inform an answer but cannot escalate permissions.

---

## 7. Agent Permissions

- Every agent has a **permission ceiling** — the highest tier it can ever reach (see §3).
  The Research Agent, for example, can never trigger a Red action.
- **Red actions are funneled to the Action Agent** and require explicit, per-action user
  approval + (for payments/account) step-up auth.
- **Standing allowances** (user-granted, per category) can streamline Yellow actions; Red
  never has an "always allow."
- Permissions are enforced **centrally** at the Orchestrator/policy engine, not trusted to
  each agent's own code.

---

## 8. Agent Lifecycle

```
Register → Receive task → Load context → Reason (LLM + tools)
        → Propose actions/memories → (policy gate: allow/prompt/block)
        → Return typed result → Orchestrator composes → Persist + audit → Idle
```

1. **Register** — agent declares its role, tools, and permission ceiling at startup.
2. **Invoke** — Orchestrator dispatches a typed task with a scoped context pack.
3. **Reason** — agent calls the LLM (model tier per task) and permitted tools.
4. **Propose** — outputs results + any proposed actions/memories (not executed directly).
5. **Gate** — the policy engine applies Green/Yellow/Red.
6. **Compose & persist** — Orchestrator merges, persists, and audits.
7. **Observe** — every run is traced and cost-tracked (Langfuse; see tech-stack).
8. **Retire/idle** — stateless; all durable state lives in memory/DB.

Agents are **stateless and ephemeral**; the memory store is the only long-lived state —
this is what makes them horizontally scalable for SaaS.

---

## 9. Future LangGraph Integration

Early phases use **custom orchestration** on the Anthropic SDK (deliberately — to master
the fundamentals; see [tech-stack.md](tech-stack.md) §8). LangGraph is the planned
evolution for complex flows:

- **Why later:** LangGraph's stateful graphs (nodes = agents/steps, edges = transitions)
  excel at multi-step, branching, retry-heavy workflows — exactly what the Research
  (Phase 4) and Builder (Phase 5) agents will need.
- **Migration is contained:** because agents already share one typed contract and the
  Orchestrator owns routing, adopting LangGraph means re-expressing *orchestration logic*
  as a graph — agents themselves don't change.
- **Selective adoption:** introduce LangGraph **per-workflow** (start with deep research),
  not as a wholesale rewrite.

---

## 10. Future Multi-Agent Orchestration

The long-horizon vision (toward Phase 14):

- **Supervisor + worker sub-graphs** — the Orchestrator spawns supervised teams for big
  tasks (e.g. "research → outline → build → review").
- **Scoped agent-to-agent delegation** — supervised, audited, permission-bounded.
- **Concurrency at scale** — parallel agent execution via the worker/queue tier.
- **Agent ecosystem / marketplace** — third-party or user-defined agents that conform to
  the contract and run inside the permission model.
- **Org-level orchestration** (business phase) — agents operating over shared, permissioned
  organizational memory.

> The throughline: a stable **contract + central policy + shared memory** today makes
> arbitrarily sophisticated orchestration possible tomorrow — without compromising
> security or requiring a rebuild.

---

_Related: [memory-system.md](memory-system.md), [security-system.md](security-system.md),
[../docs/FEATURES.md](../docs/FEATURES.md), [../docs/FUTURE_AGENTS.md](../docs/FUTURE_AGENTS.md)._
