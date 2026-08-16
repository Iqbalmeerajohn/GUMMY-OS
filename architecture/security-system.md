# GUMMY OS — Security System

> _"Gummy is powerful, so Gummy is controllable. Nothing irreversible happens without
> your say-so."_

Security and user control are foundational, not bolted on. This document defines the
**permission model** (Green / Yellow / Red), authentication, authorization, encryption,
privacy, multi-tenant SaaS security, audit logging, and user control.

> **Scope:** Design only (Phase 0). Complements the security section of
> [system-design.md](system-design.md).

---

## 1. The Permission Model (Green / Yellow / Red)

Every agent action is classified into one of three tiers by its **reversibility** and
**blast radius**. This is the heart of Gummy's "permission-based, user-controlled" promise.

### 🟢 Green Permissions — Auto-allowed
*Read-only, internal, fully reversible. No confirmation needed.*

- Research (reading/searching the web for information)
- Memory **read** (recalling what Gummy knows)
- Document **read** (reading your uploaded files)
- Generating drafts, plans, summaries (nothing sent/published)

> Green actions run freely and are logged. They cannot change the outside world or your
> account.

### 🟡 Yellow Permissions — Confirm before acting
*Writes state, creates artifacts, or has moderate impact. Reversible but consequential.
Requires a one-tap confirmation (or a standing per-category allowance).*

- Memory **write / update / delete**
- Document **write** (saving, versioning, modifying files)
- Browser **actions** (filling forms, clicking, navigating on your behalf)
- Job **application drafting / submission** (submission is borderline → defaults Yellow with explicit per-application confirm)

> Yellow actions show a clear preview ("Here's what I'll do") and a confirm button. Users
> may grant **"always allow for this category"** to streamline trusted flows.

### 🔴 Red Permissions — Explicit, per-action approval (never auto)
*External, hard-to-reverse, money, identity, or reputation. Always requires explicit
confirmation; never auto-allowed regardless of consent mode.*

- Email **sending**
- Social media **posting**
- **Payments** / financial transactions
- **Account changes** (password, security, connected integrations, deletions)
- Sharing personal data with third parties

> Red actions require an explicit, scoped, time-limited approval each time, with a full
> preview and an audit entry. No "always allow" shortcut exists for Red.

### Permission Matrix (summary)

| Action | Tier | Confirmation | "Always allow"? |
| --- | --- | --- | --- |
| Research / web read | 🟢 Green | None | n/a |
| Memory read | 🟢 Green | None | n/a |
| Document read | 🟢 Green | None | n/a |
| Memory write/update/delete | 🟡 Yellow | One-tap | Optional (per category) |
| Document write/version | 🟡 Yellow | One-tap | Optional |
| Browser actions | 🟡 Yellow | One-tap + preview | Optional (scoped) |
| Job application submit | 🟡 Yellow | Per-application | No |
| Email sending | 🔴 Red | Explicit, per-action | ❌ Never |
| Social posting | 🔴 Red | Explicit, per-action | ❌ Never |
| Payments | 🔴 Red | Explicit, per-action + re-auth | ❌ Never |
| Account changes | 🔴 Red | Explicit + re-auth | ❌ Never |

---

## 2. Authentication

- **Token-based auth** (JWT/session) verified at the API Gateway on every request.
- **Providers:** email/password + Google OAuth, issued and verified by GUMMY itself
  (HS256, audience `gummy-os`). The swappable-provider boundary was the point: the
  original Supabase Auth choice was replaced in
  [M9](../docs/10_RELEASE_NOTES_M9_LOCAL_FIRST.md) without touching the callers.
- **Step-up / re-authentication** for Red actions (payments, account changes) — a fresh
  credential check even within an active session.
- **MFA** supported (TOTP) and encouraged; required for high-risk accounts at SaaS scale.
- **Session expiry & refresh** with revocation on logout/security events.

---

## 3. Authorization

- **Tenant scoping** — every record carries `user_id` (and `organization_id` in the
  business phase). No query crosses tenants.
- **Row-Level Security (RLS)** in Postgres as defense-in-depth — the database itself
  enforces that a user can only see their own rows.
- **Agent permissions** — each agent has a declared, least-privilege set of tools and a
  permission tier ceiling (e.g. the Research Agent can never reach a Red action).
- **Per-action policy checks** — before any tool runs, the policy engine evaluates
  tier + user settings + standing allowances, then allows / prompts / blocks.
- **Org roles** (Phase 14) — owner / admin / member with permissioned shared memory.

---

## 4. Encryption

- **In transit:** TLS everywhere (HTTPS/WSS).
- **At rest:** encrypted DB, vector store, and object storage.
- **Field-level encryption** for the most sensitive data — integration tokens,
  credentials, payment references — stored as encrypted references, never plaintext.
- **Secrets management** — all keys in a dedicated secret manager / env vault; **never**
  committed to the repo (enforced by convention + CI secret scanning).
- **Memory isolation** — user memory is never used to train shared models.

---

## 5. Privacy

- **User owns their data** — full **export** and **delete** by design (GDPR-style "right
  to be forgotten"), including memories, documents, and embeddings.
- **Consent-based memory** — nothing durable is remembered without the consent flow (see
  [memory-system.md](memory-system.md) §2).
- **Pause / incognito** — a global switch to stop memory writes; ephemeral chats that are
  never persisted to long-term memory.
- **Data minimization** — Gummy stores distilled knowledge, not unnecessary raw data.
- **Transparency** — every memory and action shows its provenance.

---

## 6. Multi-Tenant SaaS Security

| Concern | Approach |
| --- | --- |
| **Isolation** | `user_id`/`org_id` scoping + Postgres RLS (DB-enforced). |
| **Noisy neighbors** | Per-user rate limits and usage quotas at the gateway. |
| **Cost/abuse** | Per-user LLM usage caps; runaway-loop guards on agents. |
| **Data leakage** | Strict context assembly — an agent only ever receives the requesting tenant's data. |
| **Secrets per tenant** | Integration tokens encrypted and scoped per user. |
| **Tenant deletion** | Cascade purge across DB, vectors, storage, and logs. |

The model is multi-tenant **from day one** (even while serving one user), so the SaaS
leap is an evolution, not a security rewrite.

---

## 7. Audit Logs

- **Every Yellow and Red action is logged** with: who, what, when, which agent, the
  permission tier, the preview shown, the decision (allowed/blocked), and the outcome.
- **Green actions** are logged at a lighter level (for observability, not approval).
- Logs are **append-only**, tenant-scoped, and queryable in the **Activity Feed** (see
  [ui-ux-system.md](ui-ux-system.md)).
- Audit logs support accountability, debugging, and (at SaaS scale) compliance.

---

## 8. User Control

The user is always in command:

- **Permission Center** — view/adjust which categories are Green/Yellow, set standing
  allowances, and review Red-action history.
- **Memory controls** — pause, consent mode, edit/delete, export, forget-everything.
- **Integration controls** — connect/disconnect accounts; revoke tokens instantly.
- **Activity Feed** — a live, human-readable log of everything Gummy did, with undo where
  possible.
- **Kill switch** — pause all agent actions immediately.

> The product principle: **the more capable Gummy becomes, the more visible and
> reversible its actions must be.**

---

## 9. Threats Considered (and mitigations)

| Threat | Mitigation |
| --- | --- |
| Prompt injection via documents/web | Treat external content as untrusted; agents can't escalate to Red via injected instructions; Red always needs human approval. |
| Cross-tenant data access | RLS + scoped context assembly + tests. |
| Credential/secret leakage | Field encryption, secret manager, CI secret scanning. |
| Runaway agent loops / cost blowups | Usage caps, loop guards, per-action policy checks. |
| Unauthorized irreversible actions | Red tier + step-up auth + audit + undo. |
| Account takeover | MFA, step-up auth, session revocation, anomaly logging. |

---

_Related: [memory-system.md](memory-system.md), [agent-framework.md](agent-framework.md)
(agent permission ceilings), [system-design.md](system-design.md)._
