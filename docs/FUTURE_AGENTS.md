# GUMMY OS — Future Agents (Exploratory Concepts)

> **Status: Exploratory.** The agents in this document are *future concepts*. They are
> **not** part of any active implementation phase in [ROADMAP.md](ROADMAP.md) and are not
> scheduled. They exist here to (a) prove the agent framework is extensible and (b) capture
> the long-term product surface before it is built.

All future agents conform to the same contract defined in
[../architecture/agent-framework.md](../architecture/agent-framework.md): they are
orchestrated by the Master Orchestrator, read/write the shared consent-based memory, route
risky actions through the Action Agent, and obey the Green/Yellow/Red permission model in
[../architecture/security-system.md](../architecture/security-system.md).

---

## 1. 📈 Marketing Agent

**Concept:** Plans and executes marketing for the user's projects, personal brand, or
(later) business.

- **Capabilities:** content strategy, campaign planning, copywriting, audience/positioning
  analysis, growth experiments, performance analytics.
- **Memory used:** Project Memory, Preference Memory, brand/voice profile.
- **Collaborates with:** Social Media Agent (distribution), Research Agent (market
  research), Personality Agent (brand voice).
- **Permissions:** drafting is 🟢/🟡; publishing/ad-spend is 🔴 (money + reputation).
- **Why future:** depends on a mature Social + Research stack and a stable brand-voice
  memory.

---

## 2. 💪 Fitness Agent

**Concept:** A personal fitness and wellbeing coach.

- **Capabilities:** workout planning, nutrition guidance, habit/goal tracking, progress
  insights, adaptive plans.
- **Memory used:** a dedicated **Health Memory** category (highly sensitive).
- **Collaborates with:** Daily Life Agent (scheduling), Vision Agent (form/photo checks).
- **Permissions:** health data is **🔴 Red-sensitive** — explicit consent for storage, never
  auto-saved, extra encryption, and clear medical-disclaimer boundaries (not a doctor).
- **Why future:** requires sensitive-data handling, possible device/wearable integrations,
  and careful safety framing.

---

## 3. 💰 Finance Agent

**Concept:** Personal finance awareness and planning assistant.

- **Capabilities:** budgeting, expense categorization, savings goals, spending insights,
  bill reminders, scenario planning.
- **Memory used:** a dedicated **Finance Memory** category (highly sensitive).
- **Collaborates with:** Daily Life Agent (reminders), Research Agent (product/rate
  research).
- **Permissions:** **🔴 Red throughout** — any transaction/payment requires explicit,
  step-up-authenticated approval; read-only insights still treat data as Red-sensitive.
- **Why future:** demands the strongest security posture, financial integrations, and
  regulatory care; deferred until the security system is battle-tested.

---

## 4. ✈️ Travel Agent

**Concept:** Plans and helps book trips end to end.

- **Capabilities:** itinerary planning, flight/hotel research, budgeting, scheduling,
  packing lists, local recommendations.
- **Memory used:** Preference Memory (travel style, budgets), Profile Memory.
- **Collaborates with:** Research Agent (options), Browser Agent (searching/booking flows),
  Daily Life Agent (calendar), Finance Agent (budget).
- **Permissions:** research/planning 🟢/🟡; **bookings & payments 🔴**.
- **Why future:** depends on Browser Agent maturity and (ideally) Finance Agent for
  payments.

---

## 5. 🛒 Shopping Agent

**Concept:** Researches products and assists with purchases.

- **Capabilities:** product research, price/spec comparison, deal tracking, wishlist
  management, reorder reminders.
- **Memory used:** Preference Memory (brands, sizes, tastes), Project/Profile Memory.
- **Collaborates with:** Research Agent (comparisons), Browser Agent (carts/checkout),
  Finance Agent (budget).
- **Permissions:** research 🟢/🟡; **checkout/payment 🔴**.
- **Why future:** requires reliable Browser automation and the payments security path.

---

## Summary Table

| Future Agent | Core value | Sensitivity | Key dependencies | Highest tier |
| --- | --- | --- | --- | --- |
| 📈 Marketing | Growth & brand | Medium | Social, Research, Personality | 🔴 (publish/spend) |
| 💪 Fitness | Health coaching | **High (health)** | Daily Life, Vision, wearables | 🔴 (health data) |
| 💰 Finance | Money clarity | **Very high** | Security maturity, integrations | 🔴 (transactions) |
| ✈️ Travel | Trip planning | Medium | Browser, Research, Finance | 🔴 (bookings) |
| 🛒 Shopping | Smart buying | Medium | Browser, Research, Finance | 🔴 (checkout) |

---

## Guiding Notes

- **Extensibility proof:** none of these required changing the framework — they slot into
  the existing contract, memory model, and permission system. That is the point.
- **Sensitivity first:** the most valuable future agents (Finance, Fitness) are also the
  most sensitive; they are deliberately deferred until the security and consent systems are
  proven in production.
- **No scheduling here:** if/when one of these is promoted, it graduates into
  [ROADMAP.md](ROADMAP.md) with its own phase, scope, and exit criteria.

---

_Related: [../architecture/agent-framework.md](../architecture/agent-framework.md),
[../architecture/security-system.md](../architecture/security-system.md),
[FEATURES.md](FEATURES.md), [ROADMAP.md](ROADMAP.md)._
