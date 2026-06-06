# GUMMY OS — Context Assembly & Claude Gateway

> How retrieved memories become a grounded answer: token-budgeted context
> assembly, a provider-abstracted LLM gateway, and the memory-aware chat pipeline.

> **Scope:** Phase 1, Day 6 — context assembly, the Claude gateway, and the chat
> pipeline **only**. No RAG framework, multi-agent orchestration, LangGraph, voice,
> or vision. **Status:** Implemented. Builds on
> [hybrid-retrieval.md](hybrid-retrieval.md) and [tech-stack.md §7](tech-stack.md).

---

## 1. The Chat Pipeline

```
user query
   │
   ▼  hybrid retrieval (semantic + importance + confidence + recency)
ranked memories
   │
   ▼  context assembly (dedupe → rank → token budget)
context package
   │
   ▼  prompt builder (system persona + memory context + user query)
prompt payload
   │
   ▼  LLM gateway (Claude, provider-abstracted)
reply
```

Each stage is a small, independently-tested unit; `chat_service` only wires them
together. The boundary is deliberate: retrieval owns *what* to remember, the
gateway owns *how* to call the model, and chat owns the *composition*.

---

## 2. Context Assembly

`assemble_context(candidates, *, token_budget, max_memories) → ContextPackage`

- **Dedupe** by normalized content, keeping the highest-scoring occurrence.
- **Rank** by the retrieval `final_score` (descending).
- **Respect a token budget** — greedily include memories until the budget
  (default 2000) is reached, always keeping at least one so an over-long top
  memory never yields an empty pack. Token cost is a cheap chars/4 estimate.
- **Output is provider-agnostic** (`ContextMemory(content, category, score)`), so
  nothing downstream touches the ORM.

## 3. Prompt Builder

`build_prompt(context, query) → PromptPayload(system, messages)`

- **System prompt** = Gummy persona + a grounding instruction + the rendered
  `<memory>` block. Stable-first ordering keeps it prompt-cache friendly later.
- **Grounding rule:** answer from the remembered context; if it isn't there, say
  so rather than guess. Plus a **"respond directly, no exploratory reasoning"**
  instruction — the recommended mitigation for Opus 4.8's tendency to narrate
  reasoning into the visible answer when thinking is off.
- **Messages** = a single `user` turn with the query (history-ready for later).

## 4. Claude Gateway (provider-abstracted)

`LLMProvider` is a Protocol with one method, `generate(system, messages, model?,
max_tokens?) → LLMResponse`. Two implementations today:

| Provider | Use |
| --- | --- |
| `ClaudeGateway` | Real Anthropic SDK (`AsyncAnthropic`). |
| `FakeLLMProvider` | Deterministic, network-free — dev/tests. |

**ClaudeGateway design** (per the Anthropic SDK guidance):

- **Async SDK**, client created lazily and reused.
- **Configurable model** — defaults to `claude-opus-4-8`; the tiered
  fast/smart/frontier ids support cost-tiering (tech-stack §7).
- **Timeout + retries** set on the client; the SDK auto-retries 429/5xx with
  backoff (`max_retries`).
- **Errors normalized to `AppError`** — timeout → 504, rate limit → 429, API/other
  → 502, missing key → 503. The API never leaks a raw 500 or a provider stack
  trace.
- **No thinking** for this short, grounded Q&A (kept simple + cheap); `max_tokens`
  defaults to 2048. Adaptive thinking can be enabled later behind config.

**Future providers (Claude · OpenAI · Gemini):** add a class implementing
`LLMProvider` and a branch in the factory — the chat service and endpoint are
unchanged.

## 5. API

`POST /api/v1/chat` — body `{ "message": "What am I preparing for?" }` →
`{ reply, model, memories_used, input_tokens, output_tokens }`.

---

## 6. Testing Strategy

- **Context assembly & prompt builder** — pure unit tests (dedupe, ranking, token
  budget, persona/memory/grounding in the system prompt).
- **Gateway** — fake provider; `ClaudeGateway` error mapping (503 unconfigured,
  502 on failure) and response normalization with an injected stub client. No
  network.
- **Chat service & API** — exercised on SQLite with the pgvector candidate fetch
  monkeypatched and the LLM gateway swapped for the fake provider, asserting the
  reply, `memories_used`, and that the memory actually landed in the system
  prompt.

---

_Related: [hybrid-retrieval.md](hybrid-retrieval.md),
[embeddings-and-search.md](embeddings-and-search.md),
[memory-system.md](memory-system.md), [tech-stack.md](tech-stack.md),
[../docs/phase-1-build-plan.md](../docs/phase-1-build-plan.md)._
