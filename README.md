# GUMMY OS

> A Personal & Business Multi-Agent AI Operating System. Your assistant's name is **Gummy**.

GUMMY OS is a long-term project to build a unified, agentic operating layer that manages
personal life, career, learning, research, building, productivity, and business
automation through a coordinated team of specialized AI agents — all backed by a
persistent, consent-based long-term memory.

**Gummy** is the assistant at the center of it: an AI companion that gradually learns you
through conversation, memory, documents, activities, preferences, and workflows — while
staying **secure, permission-based, and user-controlled**.

It is being built **first for personal use**, with a deliberate path toward a public,
multi-user **SaaS** platform.

---

## Repository Structure

```
GUMMY-OS/
├── README.md
├── CONVENTIONS.md           # Engineering & documentation standards
├── frontend/                # Web client (UI) — placeholder until Phase 1+
├── backend/                 # API, agent runtime, services — placeholder until Phase 1+
├── docs/                    # Product documentation
│   ├── VISION.md            # What GUMMY OS is and why it exists
│   ├── ROADMAP.md           # Phased delivery plan (Phase 0 → Phase 14)
│   ├── FEATURES.md          # Feature catalogue + agent descriptions
│   └── FUTURE_AGENTS.md     # Exploratory future agents (not yet scheduled)
└── architecture/            # Technical & product design
    ├── system-design.md         # High-level + agent + memory + security architecture
    ├── database-design.md       # Core data model and relationships
    ├── tech-stack.md            # Finalized technology stack (Phase 0 → 5)
    ├── memory-system.md         # Consent-based long-term memory design
    ├── conversation-system.md   # Chat history, context & session design
    ├── security-system.md       # Green/Yellow/Red permission model & SaaS security
    ├── agent-framework.md       # Master Orchestrator + agent architecture
    └── ui-ux-system.md          # The GUMMY OS experience & design language
```

## Current Status

**Phase 0 — Foundation.** This repository contains *planning, architecture, product
design, and documentation only*. No application code has been written yet — this is
intentional. See the [Phase 0 Completion Report](#) summary in chat / `docs/ROADMAP.md`.

## Where to Start

1. **Why** — [docs/VISION.md](docs/VISION.md)
2. **When** — [docs/ROADMAP.md](docs/ROADMAP.md)
3. **What** — [docs/FEATURES.md](docs/FEATURES.md)
4. **How (system)** — [architecture/system-design.md](architecture/system-design.md)
5. **How (memory)** — [architecture/memory-system.md](architecture/memory-system.md)
6. **How (agents)** — [architecture/agent-framework.md](architecture/agent-framework.md)
7. **How (security)** — [architecture/security-system.md](architecture/security-system.md)
8. **How (experience)** — [architecture/ui-ux-system.md](architecture/ui-ux-system.md)
9. **Data model** — [architecture/database-design.md](architecture/database-design.md)
10. **Stack** — [architecture/tech-stack.md](architecture/tech-stack.md)
11. **Standards** — [CONVENTIONS.md](CONVENTIONS.md)

---

> **Note on the directory name:** the folder on disk is currently `IQBAL-OS`. The product
> is now **GUMMY OS**; rename the directory to `GUMMY-OS` at your convenience (no code
> depends on it yet).

_Maintained as a single-founder project with the discipline of a startup engineering org._
