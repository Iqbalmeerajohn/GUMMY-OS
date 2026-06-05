# GUMMY OS — Conversation System

This document defines how GUMMY OS stores, organizes, searches, and contextualizes
conversations. The bar for the *storage and retrieval experience* is set by ChatGPT,
Claude, Gemini, and Perplexity — but Gummy goes further by integrating conversations
**deeply with long-term memory**.

> **Scope:** Design only (Phase 0). Data model in
> [database-design.md](database-design.md); memory integration in
> [memory-system.md](memory-system.md).

---

## 1. Design Goals

1. **Familiar, frictionless chat history** — match the best of ChatGPT/Claude/Gemini:
   persistent threads, instant switching, search, rename, archive.
2. **Memory-aware, not memory-blind** — unlike a plain chat app, every conversation both
   *reads from* and *contributes to* Gummy's long-term memory.
3. **Cheap and fast at scale** — context is assembled with summaries + retrieval, not by
   replaying entire histories into the model.
4. **Continuity across sessions** — close the app today, resume tomorrow, and Gummy still
   knows where you left off.

---

## 2. Conversation History

- Conversations are persistent **threads** (`conversations` table), each a series of
  `messages` (user / assistant / system / tool).
- Every thread is tenant-scoped (`user_id`) and ordered by `created_at`.
- Threads carry a `title` (auto-generated from the first exchange, user-editable), an
  `agent`/context tag, a rolling `summary`, and `last_message_at` for sorting.
- Status: `active` / `archived` (and soft-delete via `deleted_at`).

This mirrors the mental model users already have from ChatGPT/Claude — no relearning.

---

## 3. Chat Organization

Beyond a flat list (which is where most chat apps stop), Gummy organizes by:

| Mechanism | Description |
| --- | --- |
| **Recency groups** | Today · Yesterday · Previous 7 days · Older (Gemini/Claude-style). |
| **Agent / hub context** | Threads can be filtered by which hub they belong to (Career, Learning, Research, Builder, General). |
| **Pinned** | Important threads pinned to the top. |
| **Archived** | Out of the way but searchable. |
| **Tags / folders** *(planned)* | User-defined grouping for power users. |
| **Auto-titles** | Concise, meaningful titles generated from content. |

---

## 4. Search Conversations

A first-class capability (Perplexity/Claude-grade):

- **Keyword search** over message content (Postgres full-text).
- **Semantic search** over conversations using stored summaries' embeddings — find a
  chat by *meaning* ("that talk about RTOS scheduling") not exact words.
- **Filters** — by date range, agent/hub, pinned/archived.
- **Jump-to-message** — search results deep-link to the exact turn.

> Conversation summaries are embedded so search stays fast and cheap without indexing
> every raw message vector.

---

## 5. Conversation Summaries

Summaries are the backbone of scalable context and search:

- **Rolling summary per thread** — updated as the conversation grows (stored in
  `conversations.summary`), so long threads don't blow the context window.
- **Closing summary** — when a thread goes idle/archived, a final distilled summary is
  written and embedded.
- **Memory promotion** — durable facts surfaced in a conversation are proposed as
  long-term **Conversation Memory** (see [memory-system.md](memory-system.md) §3.1),
  subject to the user's consent mode.

```
long thread → rolling summary keeps context small
            → durable facts → proposed as memory (consent-gated)
            → closing summary → embedded for future semantic search
```

---

## 6. Context Retrieval (per turn)

For each user message, Gummy assembles a **token-budgeted context pack**:

```
1. System / personality prompt (Personality Agent).
2. Recent messages from THIS thread (short-term/working memory).
3. The thread's rolling summary (older context, compressed).
4. Relevant long-term memories (Memory Service hybrid retrieval).
5. Relevant document chunks (if the query touches uploaded files).
6. Tool/agent outputs as needed.
```
This layered strategy means Gummy stays coherent over very long histories **without**
resending everything — controlling both latency and LLM cost.

---

## 7. Session Handling

- **Stateless backend, stateful store** — sessions are reconstructed from the DB, so any
  device/instance can resume a conversation (essential for SaaS + future mobile).
- **Resume-where-you-left-off** — reopening a thread restores recent messages + summary
  instantly.
- **Multi-device** — the same account sees the same threads everywhere (Phase 13 mobile
  inherits this for free).
- **Auth-scoped** — every session is tied to an authenticated user; tokens verified at
  the gateway (see [security-system.md](security-system.md)).

---

## 8. Long-Term Context Strategy

How Gummy "remembers conversations" across weeks and months:

| Horizon | Mechanism | Cost |
| --- | --- | --- |
| **Within a turn** | Full recent messages in context | low |
| **Within a thread** | Rolling summary + recent messages | low |
| **Across threads** | Semantic recall of conversation summaries + promoted memories | low (retrieval) |
| **Lifetime** | Long-term memory store (facts, preferences, projects) | low (retrieval) |

The key architectural choice: **conversations are the *raw material*; memory is the
*distilled product*.** Chat history gives continuity and audit; long-term memory gives
true cross-session intelligence. Together they make Gummy feel like it never forgets —
while keeping every model call lean.

---

## 9. How Gummy Differs From a Plain Chat App

| Capability | ChatGPT/Claude/Gemini (baseline) | GUMMY OS |
| --- | --- | --- |
| Persistent threads | ✅ | ✅ |
| Search history | ✅ (varies) | ✅ keyword **+ semantic** |
| Summaries | partial | ✅ rolling + closing, embedded |
| Long-term memory | limited / opt-in | ✅ structured, consent-based, categorized |
| Cross-agent context | ❌ | ✅ shared memory across all agents |
| User-owned memory dashboard | ❌ / minimal | ✅ full Memory Center |

---

_Related: [memory-system.md](memory-system.md), [database-design.md](database-design.md),
[ui-ux-system.md](ui-ux-system.md) (AI Workspace & history UI)._
