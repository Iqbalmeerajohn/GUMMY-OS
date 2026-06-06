# GUMMY OS — Memory System

> _"Gummy remembers what matters — only what you allow, exactly as you intend, and never
> more."_

Memory is the moat of GUMMY OS. It is what turns Gummy from a chatbot into a companion
that genuinely *knows you*. This document defines the philosophy, lifecycle, scoring,
retrieval, and user-facing surfaces of the memory system.

> **Scope:** Design only (Phase 0). Backed by the data model in
> [database-design.md](database-design.md) and the architecture in
> [system-design.md](system-design.md).

---

## 1. Memory Philosophy

1. **Memory is earned, not assumed.** Gummy does not silently hoover up everything. A
   fact becomes long-term memory through an explicit or clearly-consented path.
2. **The user owns the memory.** Every memory is viewable, editable, and deletable by the
   user. There are no hidden memories.
3. **Memory is structured, not a transcript.** Gummy stores *distilled knowledge* (facts,
   preferences, summaries) — not raw chat logs masquerading as memory.
4. **Memory has confidence and importance.** Not all memories are equal; Gummy tracks how
   *sure* it is and how *much it matters*.
5. **Memory decays and updates.** Outdated facts are superseded; stale, low-value
   memories fade. Memory reflects who you are *now*.
6. **Memory is private by construction.** Every memory is tenant-scoped and encrypted; it
   is never used to train shared models.

---

## 2. Consent-Based Memory

Gummy supports three consent modes, user-configurable in Settings:

| Mode | Behavior | Default |
| --- | --- | --- |
| **Explicit** | Gummy only saves memory when the user says so ("remember this") or confirms a suggestion. | Recommended for privacy-first users |
| **Assisted** (default) | Gummy proposes memories ("Want me to remember that you're targeting Qualcomm?"); user one-taps to accept. | ✅ Default |
| **Autonomous** | Gummy auto-saves clearly durable facts and notifies the user, who can undo. | Power users |

**Consent rules (all modes):**
- Sensitive categories (health, finance, credentials) are **never** auto-saved — always
  explicit, regardless of mode.
- Every memory records *how it was created* (`source` + `consent_mode`) for transparency.
- A single global switch — **"Pause memory"** — stops all new memory writes instantly.

---

## 3. Memory Lifecycle

### 3.1 Memory Creation
A memory can be created from four triggers:

1. **Direct command** — "Remember that I'm preparing for Qualcomm."
2. **Suggested + accepted** — Gummy detects a durable fact and offers to save it.
3. **Document-derived** — ingesting a resume/file extracts structured memories.
4. **Activity-derived** — completing a job application or research report writes memory.

Creation pipeline:
```
Candidate fact → classify type → score importance + confidence → check consent
→ dedupe against existing memories → embed → store (row + vector) → confirm/notify
```

### 3.2 Memory Updates
- **Supersession, not silent overwrite.** When a newer fact conflicts ("I switched my
  target from Qualcomm to NVIDIA"), the old memory is marked `superseded`, the new one
  links back via `supersedes_id`, preserving history.
- **Reinforcement.** Re-encountering a fact raises its `confidence` and `importance` and
  refreshes `last_recalled_at` (the memory feels "stickier").

### 3.3 Memory Deletion
- **Soft delete first** (`deleted_at` set) — recoverable for a grace window.
- **Hard delete on request** — permanent purge of the row, its embedding, and any
  derived chunks (honoring the "right to be forgotten").
- **Cascade clarity** — deleting a source document offers to delete memories derived from
  it.

---

## 4. Scoring

### 4.1 Confidence Score (0.0–1.0)
*How sure is Gummy this is true?*
- Direct user statement → high (0.9–1.0).
- Inferred from behavior/context → medium (0.5–0.7).
- Weak/ambiguous signal → low (< 0.5), never auto-saved.
- Raised by reinforcement, lowered by contradiction.

### 4.2 Importance Score (0.0–1.0)
*How much does this matter to serving the user?*
- Goals, identity, active projects → high.
- Stable preferences → medium-high.
- Trivia / one-off context → low.
- Decays over time unless reinforced (recency-weighted).

### 4.3 Memory Ranking (retrieval-time)
Final relevance for a given query combines:
```
score = w1·semantic_similarity
      + w2·importance
      + w3·recency
      + w4·confidence
      + w5·category_match
```
Weights are tunable; this hybrid ranking prevents both "forgot the obvious" and "drowned
in trivia" failure modes.

---

## 5. Versioning

### 5.1 Resume Versioning
The user's resume is a first-class, versioned artifact (critical for the Career Agent):
- Each upload creates a **new version** (`resume_v1`, `resume_v2`, …); old versions are
  retained, not replaced.
- Gummy diffs versions ("new resume adds a Qualcomm internship and drops the 2022
  project") and updates Career Memory accordingly.
- The **active version** is user-selectable; tailored resumes per job reference a base
  version.

### 5.2 Document Versioning
- Any re-uploaded or edited document is versioned the same way (immutable versions +
  pointer to current).
- Memories derived from a document record which **version** they came from, so recall is
  never silently wrong after an update.

---

## 6. Memory Retrieval Pipeline

Runs on every Gummy turn that needs context:

```
1. Parse the user request + active conversation.
2. Classify which memory categories are relevant (e.g. Career + Profile).
3. Hybrid search:
      a. Vector similarity over embeddings (pgvector)
      b. Metadata filters (user_id, category, not-deleted, not-superseded)
      c. Full-text match for exact terms
4. Rank by the combined score (§4.3).
5. Assemble a token-budgeted context pack (top-K + summaries).
6. Inject into the agent prompt; record last_recalled_at on used memories.
```
The Memory Service abstracts this so every agent recalls memory the same way.

---

## 7. Memory Categories (Types)

| Category | What it holds | Example | Typical source |
| --- | --- | --- | --- |
| **Profile Memory** | Identity: name, location, role, background | "Final-year ECE student in Bangalore" | onboarding, conversation |
| **Preference Memory** | Tastes, working style, communication prefs | "Prefers concise, bullet-point answers" | assisted/auto |
| **Career Memory** | Goals, target companies, skills, applications | "Targeting Qualcomm for an embedded role" | command, resume |
| **Learning Memory** | Skills in progress, curricula, mastery | "Learning RTOS; 60% through the plan" | Learning Agent |
| **Project Memory** | Active builds, decisions, status | "Building GUMMY OS; in Phase 0" | Builder Agent |
| **Conversation Memory** | Distilled summaries of past chats | "Discussed RAG design on Jun 4" | summarization |
| **Document Memory** | Knowledge extracted from uploaded files | "Resume v2: 2 internships, 5 projects" | ingestion |

Each maps to `memories.type` / `category` in the schema, enabling category-scoped recall
and dashboard filtering.

---

## 8. Memory Dashboard ("Memory Center")

The user-facing control surface (see [ui-ux-system.md](ui-ux-system.md)):

- **Browse by category** with confidence/importance badges.
- **Search & filter** memories (semantic + keyword).
- **Inspect provenance** — for each memory: source, created date, consent mode, version.
- **Edit / correct / delete** any memory inline.
- **Version history** for resume and documents.
- **Memory health** — counts, recently added, low-confidence items to review.
- **Global controls** — pause memory, set consent mode, export, "forget everything".

> The dashboard is the embodiment of "the user owns the memory." Transparency is a
> feature, not an afterthought.

---

## 9. Real Workflows

### Workflow A — "I am preparing for Qualcomm." → "Remember that."
```
User:  "I am preparing for Qualcomm." ... "Remember that."
Gummy: classifies → Career Memory.
       importance: high (active goal) · confidence: high (direct statement).
       dedupe: no conflicting target found.
       → creates memory: {type: career, content: "Targeting Qualcomm", consent: explicit}
Gummy: "Saved. I'll tailor your job search, prep, and resume toward Qualcomm. 🎯"
```
Effect: the Career, Learning, and Research agents now bias toward Qualcomm.

### Workflow B — "What do you know about me?"
```
User:  "What do you know about me?"
Gummy: retrieves top memories across categories, grouped:
       Profile  · Final-year ECE student, Bangalore
       Career   · Targeting Qualcomm (embedded), resume v2 active
       Learning · Studying RTOS (60%)
       Prefs    · Likes concise answers, dark mode
Gummy: presents the summary + "Manage these in your Memory Center →"
```
Effect: pure recall from the memory store; nothing fabricated; everything editable.

### Workflow C — "I uploaded a new resume."
```
User:  uploads resume.pdf
Gummy: ingest → parse → diff vs resume_v1
       → creates resume_v2 (active), keeps v1
       → updates Career Memory: + "Qualcomm internship (2025)"
       → flags: "Your old summary line is now outdated — update it?"
Gummy: "Got your new resume (v2). I noticed a new Qualcomm internship and updated your
        career profile. Want me to retire the old objective line?"
```
Effect: versioned, diff-aware ingestion that keeps memory current without data loss.

### Workflow D — Correcting / forgetting
```
User:  "Actually I'm targeting NVIDIA now, not Qualcomm."
Gummy: marks Qualcomm memory superseded; creates NVIDIA memory linked via supersedes_id.
Gummy: "Updated — now targeting NVIDIA. I kept the history in case you switch back."
```

---

## 10. Implementation Notes (forward-looking)

- Backed by Postgres + pgvector (see [tech-stack.md](tech-stack.md)); the Memory Service
  is a **custom layer** Gummy owns (not outsourced) — the core learning + moat.
- Summarization/compaction uses a cheap model tier; recall ranking is mostly cheap math.
- Every write and recall is **tenant-scoped** and audit-logged (see
  [security-system.md](security-system.md)).
- Sensitive categories follow the **Red permission** path before any storage.
- **Embeddings & semantic recall** (model choice, `memory_embeddings`, pgvector cosine
  search) are specified in [embeddings-and-search.md](embeddings-and-search.md).

---

_Related: [conversation-system.md](conversation-system.md) (how chats feed memory),
[agent-framework.md](agent-framework.md) (who reads memory),
[security-system.md](security-system.md) (how memory is protected)._
