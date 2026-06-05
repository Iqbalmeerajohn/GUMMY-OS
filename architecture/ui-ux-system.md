# GUMMY OS — UI / UX System

> **GUMMY OS must NOT look like ChatGPT.** This is an **AI Operating System**, not a chat
> window. Chat is *one panel* inside a living, spatial, animated workspace.

This document defines the product design, brand identity, design language, and the core
surfaces of the GUMMY OS experience.

> **Scope:** Product/UX design only (Phase 0). No code. Future implementation:
> Next.js + Tailwind + Framer Motion + shadcn/ui (see [tech-stack.md](tech-stack.md)).

---

## 1. Design Principles

1. **An OS, not a chatbox.** The primary metaphor is a *dashboard / workspace*, with
   hubs, panels, and an ever-present assistant — not an endless message list.
2. **Animated & alive.** Gummy feels present through organic motion: soft pulses, smooth
   transitions, responsive micro-interactions. Motion communicates state, never decorates
   emptily.
3. **Minimal & clean.** Calm, uncluttered, generous whitespace. Power lives one tap away,
   not crammed on screen.
4. **Friendly & soft.** Rounded, gummy, approachable — intelligence that feels warm, not
   clinical.
5. **Futuristic.** Dark-first, glowing green accents, depth and glass — a "JARVIS"
   atmosphere.
6. **Adaptive & mobile-friendly.** Layouts reflow gracefully from desktop OS-feel to a
   focused mobile companion.

---

## 2. Brand Identity — the "GUMMY" concept

The name *Gummy* drives the entire visual identity:

| Brand idea | Meaning | Visual expression |
| --- | --- | --- |
| **Sticky memory** | Things you tell Gummy *stick*. | Memories as soft "blobs"/cards that snap, cling, and cluster; subtle stickiness in drag/drop. |
| **Connected experiences** | Agents, memory, and hubs are one organism. | Flowing connective lines/nodes; a living "memory graph" motif. |
| **Smooth flows** | Everything transitions, nothing jumps. | Eased, springy motion (Framer Motion); morphing panels. |
| **Soft intelligence** | Powerful but gentle and human. | Rounded geometry, soft shadows/glow, gummy bounce easing. |

**Mascot/presence:** Gummy is represented by a soft, organic orb/blob that breathes,
pulses while thinking, and reacts to interaction — the emotional anchor of the OS.

---

## 3. Design Language

- **Theme:** **Dark-first** (deep near-black/charcoal base), optional light mode later.
- **Accent system:** **green-inspired** — a vibrant "gummy green" primary with a small
  supporting palette (mint/teal highlights, soft glow). Green = Gummy's signature and
  doubles as the security "Green permission" language.
- **Shape:** generous rounded corners, pill buttons, blob-like containers.
- **Depth:** layered glass/elevation, soft shadows, subtle gradients and glow.
- **Motion:** **organic, springy easing**; thinking states animate the Gummy orb;
  panels morph and slide; lists stagger in. (Respect `prefers-reduced-motion`.)
- **Typography:** a clean, modern, friendly sans (geometric, slightly rounded) with clear
  hierarchy.
- **Iconography:** rounded, consistent, minimal line/solid set.

> **Accent ≠ ChatGPT green.** The palette is intentionally Gummy's own — saturated, glowing,
> paired with dark glass — to read as a futuristic OS, not a chat app.

---

## 4. Core Surfaces

Eleven surfaces compose the GUMMY OS experience. Each is a "room" in the OS.

### 4.1 Dashboard (Home)
The command center — the first thing you see.
- Greeting from Gummy (orb + status) and a "What can I do for you?" prompt.
- **Glanceable widgets:** active goals, today's tasks, recent memories, agent activity,
  career/learning/research snapshots.
- Quick-launch into any hub or a new conversation.
- Feels like a *mission control*, not a blank chat.

### 4.2 AI Workspace
Where you converse and co-work with Gummy.
- Conversation thread **+ a side context rail** showing what Gummy is using (recalled
  memories, documents, the active agent) — transparency made visual.
- Streaming responses with the orb "thinking" animation.
- Thread history (Today/Yesterday/Older), search (keyword + semantic), pin/archive.
- **Not** a full-screen chat — chat is framed inside the workspace with context around it.

### 4.3 Memory Center
The embodiment of "you own your memory" (see [memory-system.md](memory-system.md) §8).
- Memories as **sticky cards/blobs**, grouped by category (Profile, Career, Learning…).
- Confidence/importance badges; provenance on each card.
- Edit / correct / delete inline; resume & document **version history**.
- A **memory graph** view showing connections; global controls (pause, consent mode,
  export, forget).

### 4.4 Career Hub
Home of the Career Agent.
- Job pipeline board (saved → applied → interviewing → offer).
- Resume versions + tailored variants; match scores.
- Application drafts, interview prep, outreach.

### 4.5 Learning Hub
Home of the Learning Agent.
- Active skills/curricula with progress rings.
- Spaced-repetition review queue.
- Learning sourced from documents and research.

### 4.6 Research Hub
Home of the Research Agent.
- Research reports library (searchable, citeable).
- Live multi-step research progress visualization.
- Sources panel with credibility cues.

### 4.7 Agent Center
The OS's "app drawer" for agents.
- All agents shown as living tiles (status: idle / working / needs-approval).
- Enable/disable agents; view each agent's permissions and recent activity.
- Surfaces the multi-agent nature of the OS explicitly.

### 4.8 Settings
- Profile, personality tuning (Gummy's tone/voice), theme.
- **Permission Center** (Green/Yellow/Red, standing allowances) — see
  [security-system.md](security-system.md).
- Integrations (connect/disconnect, revoke), privacy controls, model preferences,
  usage/limits.

### 4.9 Notifications
- Proactive nudges, approval requests (Yellow/Red), agent completions.
- Clear, actionable, dismissible; respects quiet hours.

### 4.10 Activity Feed
- A live, human-readable log of everything Gummy did (the audit trail, humanized).
- Filter by agent/tier; **undo** where possible.
- Trust through visibility.

### 4.11 Document Workspace
- Upload, view, and manage documents; version history.
- See extracted Document Memory and ask Gummy about any file.
- Drag-to-memory and document-aware chat.

---

## 5. Layout & Navigation

- **Desktop:** a persistent left **hub rail** (Dashboard, Workspace, Memory, Career,
  Learning, Research, Agents, Documents, Activity, Settings) + a contextual right panel +
  the ever-present Gummy orb (summonable anywhere, like a system assistant).
- **Mobile:** bottom nav for the top hubs; the orb as a floating action presence; panels
  become full-screen, swipeable sheets. Adaptive, thumb-friendly.
- **Command palette** (⌘/Ctrl-K): jump to any hub, action, or memory instantly — an OS-grade
  accelerator.

---

## 6. Signature Interactions (the "Gummy feel")

- **The Orb** — breathes when idle, pulses/ripples when thinking, reacts to voice.
- **Sticky memory** — saving a memory animates a blob "sticking" into the Memory Center.
- **Morphing panels** — hubs expand/collapse with springy, eased motion.
- **Connective flows** — when agents collaborate, animated links show data flowing between
  them and memory.
- **Approval moments** — Yellow/Red confirmations slide in as clear, friendly cards with a
  preview, never a scary modal.

---

## 7. Accessibility & Quality Bar

- WCAG AA contrast even in dark mode; never rely on color alone (the Green/Yellow/Red
  tiers also carry icons + labels).
- Full keyboard navigation + command palette.
- `prefers-reduced-motion` disables non-essential animation.
- Responsive from large desktop to small mobile; touch targets sized for thumbs.
- Fast perceived performance: skeletons, optimistic UI, streaming.

---

## 8. What We Are Explicitly NOT Building

- ❌ A full-screen, single-column chat clone.
- ❌ A clinical, gray, enterprise dashboard.
- ❌ Static, motionless screens.
- ✅ A warm, animated, spatial **AI Operating System** where chat is one tool among many,
  memory is visible and tangible, and Gummy feels *present*.

---

_Related: [memory-system.md](memory-system.md) (Memory Center),
[security-system.md](security-system.md) (Permission Center / Activity Feed),
[agent-framework.md](agent-framework.md) (Agent Center), [tech-stack.md](tech-stack.md)
(Next.js + Tailwind + Framer Motion + shadcn/ui)._
