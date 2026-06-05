# GUMMY OS — Brand System

> The single source of truth for how GUMMY OS **looks, moves, and feels**. It turns the
> principles in [ui-ux-system.md](ui-ux-system.md) into concrete, buildable design tokens.

> **Scope:** Brand identity + design tokens (Phase 0). No code. Implementation target:
> Tailwind CSS theme + shadcn/ui + Framer Motion (see [tech-stack.md](tech-stack.md)).
> Tokens below are **named decisions**, not final hex law — they seed the Tailwind config
> and may be tuned in Phase 1 against real screens. Status: **Locked (palette intent),
> Tunable (exact values).**

---

## 1. Brand Essence

GUMMY OS is a **warm, alive AI Operating System** — not a chat app. The brand must read as
*futuristic, soft, and present*. Four words govern every decision:

| Word | Meaning | Design consequence |
| --- | --- | --- |
| **Sticky** | What you tell Gummy *sticks*. | Blob/card shapes that cling, snap, cluster. |
| **Alive** | Gummy is present, breathing, reactive. | Organic motion; the orb as emotional anchor. |
| **Soft** | Powerful but gentle and human. | Rounded geometry, soft glow, gummy easing. |
| **Futuristic** | A JARVIS-grade OS. | Dark-first, glass depth, glowing green accents. |

> **Anti-goal:** must NOT look like ChatGPT (full-screen single-column chat) or a clinical
> gray enterprise dashboard. See [ui-ux-system.md §8](ui-ux-system.md).

---

## 2. Logo & Mascot — the Orb

**Gummy is represented by a soft, organic orb/blob** — the brand's mascot and the system's
living presence.

- **Idle:** slow "breathing" scale pulse (~4s loop), gentle inner glow.
- **Thinking:** faster pulse + rippling concentric rings while a response streams.
- **Listening (voice, Phase 12):** reactive amplitude ripple.
- **Form:** not a perfect circle — a subtly morphing, gummy blob (squash-and-stretch).
- **Reduced motion:** the orb holds a static glow state (respect `prefers-reduced-motion`).

The wordmark pairs **"GUMMY"** (display weight) with **"OS"** (lighter) and may sit beside
the orb. The orb alone is the app icon / favicon / loading state.

---

## 3. Color System

**Dark-first.** A deep near-black canvas with a vibrant **"gummy green"** signature. Green
is doubly meaningful: it is Gummy's brand color *and* the "Green = safe/allowed" tier in
the [security model](security-system.md). Accent is intentionally **not** ChatGPT green —
more saturated, glowing, and paired with dark glass.

### 3.1 Brand & accent

| Token | Role | Value (seed) |
| --- | --- | --- |
| `--gummy-green-500` | Primary accent / brand | `#22E07A` |
| `--gummy-green-400` | Hover / lighter accent | `#46EB92` |
| `--gummy-green-600` | Pressed / deeper accent | `#13B863` |
| `--gummy-mint-300` | Supporting highlight | `#7CF5C0` |
| `--gummy-teal-400` | Secondary cool highlight | `#2DD4BF` |
| `--gummy-glow` | Accent glow (shadows/auras) | `rgba(34, 224, 122, 0.35)` |

### 3.2 Surfaces (dark-first canvas & glass)

| Token | Role | Value (seed) |
| --- | --- | --- |
| `--bg-base` | App background (near-black) | `#0A0E0C` |
| `--bg-elevated` | Panels / cards | `#121815` |
| `--bg-glass` | Glass layer (with blur) | `rgba(18, 24, 21, 0.6)` |
| `--border-subtle` | Hairline separators | `rgba(255, 255, 255, 0.08)` |
| `--text-primary` | Primary text | `#ECFDF5` |
| `--text-secondary` | Muted text | `#94A3A0` |

### 3.3 Semantic — Permission tiers (must match the security model)

These are **functional, not decorative**, and always pair color with an icon + label
(never color alone — accessibility, see §7).

| Tier | Meaning | Token | Value (seed) |
| --- | --- | --- | --- |
| 🟢 **Green** | Auto-allowed / safe | `--tier-green` | `#22E07A` |
| 🟡 **Yellow** | Needs confirmation | `--tier-yellow` | `#F5C542` |
| 🔴 **Red** | High-risk / explicit approval | `--tier-red` | `#F0506E` |
| ℹ️ **Info** | Neutral system info | `--tier-info` | `#5AB0F5` |

> Green serving both "brand accent" and "safe tier" is intentional — the OS *feels* safe by
> default. Where the two could be confused (e.g. a Green-tier badge on a green button), the
> tier badge always carries its icon + label to disambiguate.

---

## 4. Typography

A clean, modern, friendly **geometric sans** with slightly rounded terminals — matching the
"soft intelligence" identity.

| Token | Role | Choice (seed) |
| --- | --- | --- |
| `--font-display` | Headings, wordmark, orb states | Space Grotesk / Cabinet Grotesk |
| `--font-sans` | Body & UI | Inter (or Geist Sans) |
| `--font-mono` | Code, tokens, IDs, logs | JetBrains Mono / Geist Mono |

**Scale (rem, 1.250 major-third):** `xs 0.75 · sm 0.875 · base 1.0 · lg 1.25 · xl 1.563 ·
2xl 1.953 · 3xl 2.441`. Hierarchy is carried by weight + size, not by many colors.

---

## 5. Shape, Depth & Spacing

- **Radius (gummy roundness):** `sm 8px · md 14px · lg 22px · xl 32px · pill 9999px`.
  Buttons are pills; cards/panels are `lg`+; containers lean blob-like.
- **Elevation:** soft, diffuse shadows + accent glow on interactive/active elements.
  `--shadow-soft: 0 8px 30px rgba(0,0,0,0.35)`; `--shadow-glow: 0 0 24px var(--gummy-glow)`.
- **Glass:** `backdrop-blur` over `--bg-glass` with a `--border-subtle` hairline.
- **Spacing:** 4px base grid (`1=4px … 6=24px … 10=40px`); generous whitespace by default.

---

## 6. Motion — the "Gummy Feel"

Motion **communicates state, never decorates emptily**. Springy, organic easing is the
brand's signature gesture. Implemented with **Framer Motion**.

| Token | Use | Value (seed) |
| --- | --- | --- |
| `--ease-gummy` | Default springy ease | `cubic-bezier(0.34, 1.56, 0.64, 1)` (overshoot) |
| `--ease-smooth` | Calm transitions | `cubic-bezier(0.4, 0, 0.2, 1)` |
| `--dur-fast` | Micro-interactions | `150ms` |
| `--dur-base` | Panel/card transitions | `300ms` |
| `--dur-orb` | Orb breathing loop | `4000ms` |

**Signature interactions** (from [ui-ux-system.md §6](ui-ux-system.md)): the breathing
**Orb**, **sticky memory** (a blob "sticks" into the Memory Center on save), **morphing
panels**, **connective flows** between collaborating agents, and friendly slide-in
**approval moments** for Yellow/Red actions.

> **Always** gate non-essential motion behind `prefers-reduced-motion`.

---

## 7. Accessibility Guardrails

- **WCAG AA contrast** for text/UI, even in dark mode — verify seed values against real
  backgrounds in Phase 1 and adjust tokens, not the rule.
- **Never color alone:** permission tiers and statuses always carry an icon + text label.
- **Full keyboard** navigation + command palette (⌘/Ctrl-K); visible focus rings using the
  accent glow.
- **Reduced motion** disables breathing/ripples/overshoot; transitions degrade to fades.
- **Touch targets** ≥ 44px on mobile.

---

## 8. Token → Tailwind Mapping (Phase 1 hand-off)

When the frontend is scaffolded, these tokens become:

- CSS custom properties in a global stylesheet (`:root`, dark by default).
- The `theme.extend` block of `tailwind.config.ts` (`colors`, `borderRadius`,
  `boxShadow`, `fontFamily`, `transitionTimingFunction`).
- shadcn/ui theme variables wired to the same custom properties.
- Framer Motion transition presets (`gummy`, `smooth`) sharing `--ease-*`/`--dur-*`.

This keeps design and code reading from **one** token vocabulary.

---

_Related: [ui-ux-system.md](ui-ux-system.md) (experience & surfaces),
[security-system.md](security-system.md) (Green/Yellow/Red tiers),
[tech-stack.md](tech-stack.md) (Next.js + Tailwind + Framer Motion + shadcn/ui)._
