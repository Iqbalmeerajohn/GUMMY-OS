# The Tool System

How GUMMY lets an agent *do* things, and what stops it doing the wrong ones.

This describes what exists today. Anything not implemented is marked as such.

---

## 1. The shape

```
user message
   ↓
orchestrator → router → agent
   ↓
agent + its declared tools → model
   ↓
   ├── final answer                          → done
   └── tool call(s)
         ↓  registry lookup
         ↓  policy gate (manifest + tier)
         ↓  schema validation
         ↓  execute, under a timeout
         ↓  audit row
         ↓  result fed back to the model
         └── repeat, up to the iteration cap
```

The path is always `agent → registry → policy → executor → implementation`.
An agent never imports a tool implementation, and nothing bypasses the gate.

---

## 2. Tool contract

Tools are code-defined in `app/services/agents/tools/catalog.py` as `ToolSpec`:

| Field | Meaning |
| --- | --- |
| `key` | Stable identifier, e.g. `file_search` |
| `display_name` | Human label shown in the UI |
| `description` | What the model is told the tool does |
| `category` | `compute` · `memory` · `files` · `research` · `utility` · `communication` |
| `tier` | GREEN / YELLOW / RED |
| `parameters` | JSON Schema for the arguments |
| `executor` | The implementation, or `None` for a *modeled* tool |
| `timeout_seconds` | Enforced by the executor, not the tool |

**Only `key`, `description`, and `parameters` ever reach the model.** Tier,
timeout, and executor are internal — `to_function_schema()` is the single place
that decides what is exposed, and a test asserts nothing else leaks.

A tool with `executor=None` is **modeled**: declared, routed, and gated, but it
cannot run. That is how YELLOW/RED capability is described before the approval UI
exists without ever firing a risky action. Modeled tools are withheld from the
model entirely — offering a capability that can only be refused invites a call
that wastes a turn.

---

## 3. Registry

`catalog.py` is the single registry. Surface:

```python
exists(key)          # is this a known tool?
get(key)             # spec or None
list_tools(category) # everything, optionally filtered
resolve(keys)        # specs for keys, silently dropping unknown ones
function_schemas(keys)  # model-facing schemas, executable tools only
```

`resolve` drops unknown keys rather than raising: a manifest naming a removed
tool should cost that agent one capability, not every turn it serves.

---

## 4. Risk tiers

| Tier | Rule | Tools today |
| --- | --- | --- |
| **GREEN** | Read-only / reversible. Auto-allowed. | `calculator`, `current_time`, `memory_read`, `file_search`, `file_list`, `web_search`, `doc_read` |
| **YELLOW** | Consequential. Requires confirmation; a standing allowance may pre-authorise. | `email_send` *(modeled)* |
| **RED** | Irreversible / sensitive. **Always** per-action approval; standing allowances are ignored. | `social_publish` *(modeled)* |

The policy engine (`policy_engine.py`) evaluates only **trusted state**: the
code-defined agent manifest, the code-defined catalog tier, and the user's
settings. Nothing a model or a tool produces can influence a verdict. That is the
prompt-injection boundary, and it is structural rather than instructional.

Rules, in order:

1. tool not in the agent's manifest → **BLOCK**
2. tool tier above the agent's ceiling → **BLOCK**
3. GREEN → **ALLOW**
4. YELLOW → **ALLOW** with a standing allowance, else **PROMPT**
5. RED → **PROMPT**, always

---

## 4b. Web search: the four outcomes

`web_search` is the one tool whose *absence of a result* is as important as its
result, so it does not return a bare list.

```
             is a live provider installed?
                    /            \
                  no              yes
                   |                |
             UNAVAILABLE      did the query succeed?
                                /            \
                             no               yes
                              |                 |
                           FAILED        any hits after dedupe?
                                            /        \
                                          no          yes
                                           |            |
                                     NO_RESULTS     AVAILABLE
```

These were one empty list before. A caller that cannot tell them apart has to
guess which it is looking at, and the guess that gets made is "the web contains
nothing about this" — a statement about the world, made on the strength of our
own timeout.

**Provider:** Tavily (`TavilySearchProvider`), `POST https://api.tavily.com/search`,
key sent as a bearer token rather than in the JSON body — a request body is the
thing most likely to be echoed back in an error or captured by a debug log.
Requires **both** `TAVILY_API_KEY` and `AGENTS_WEB_SEARCH_ENABLED=true`;
`init_provider` at the composition root (`app/main.py`) installs it and leaves
the offline `DummySearchProvider` in place otherwise. There is one search seam
for the whole codebase — the tool and the knowledge-fusion path both go through
`search_service`.

Results map `title` → title, `url` → url, `content` → snippet, with `source`
set to `tavily` so citations name the provider internally while the user only
ever sees the **websites**.

**The placeholder is never evidence.** `DummySearchProvider` returns clearly
labelled mock rows so the wiring can be tested without a key. It was once
reported to the model as a successful search, and the model relayed the mocks
to the user as findings. `search_outcome` now returns `UNAVAILABLE` when the
placeholder is installed, and the tool raises rather than returning rows.

**Keys never leave the backend.** The failure message carries the exception
type only — provider error bodies sometimes echo the credential back —
and the key appears in no log, trace, tool result or API response. Pinned by
tests.

---

## 5. Executor

`executor.py` owns everything between "the call is permitted" and "here is what
happened":

- **Validation** against the declared schema — required keys and top-level
  types. Unknown keys are dropped (models add plausible extras; failing the call
  for that trades a working answer for a pedantic one), and `"5"` is coerced to
  `5` for integer fields.
- **Timeout**, enforced here so a tool cannot opt out of it.
- **Outcome**, never an exception:

| Outcome | Meaning |
| --- | --- |
| `SUCCESS` | Ran, returned output |
| `FAILED` | Raised, or arguments were invalid |
| `TIMEOUT` | Exceeded its budget |
| `DENIED` | Policy refused it (unknown tool, not in manifest, above ceiling) |
| `APPROVAL_REQUIRED` | Pending human decision |
| `UNAVAILABLE` | Declared but not runnable in this build |

Every outcome — including the refusals — is fed back to the model. An agent told
"that needs approval" can explain itself; an agent told nothing invents a result.

---

## 6. The loop

`loop.py`. Three bounds, each for a different failure:

| Bound | Constant | Default | Guards against |
| --- | --- | --- | --- |
| Iterations | `MAX_TOOL_ITERATIONS` | 4 | A model that keeps calling instead of answering |
| Calls per step | `MAX_TOOL_CALLS_PER_STEP` | 3 | A fan-out that multiplies latency and blast radius |
| Per-tool timeout | `ToolSpec.timeout_seconds` | 5–20s | A wedged tool holding the turn open |

On its final permitted iteration the model is told it has no tool calls left and
asked to answer with what it has, so the cap produces a real answer rather than a
truncated thought. If it still produces nothing, the loop says so plainly.

The loop is skipped entirely when the agent declares no tools or the provider
cannot call them — a normal turn, no special case for callers.

---

## 7. Streaming events

The chat stream carries progress alongside the reply. **No chain-of-thought, no
prompts, no tool arguments.**

| Event | Fields |
| --- | --- |
| `status` | `stage` (`understanding`, `retrieving_context`, `gathering`, `delegating`, `answering`), `agent` |
| `tool_status` | `stage` (`tool_requested`, `tool_running`, `tool_completed`, `tool_failed`, `approval_required`), `tool`, `label`, `duration_ms` |
| `delta` | reply text |
| `done` | ids, model, `stages`, `tools`, memories, web sources |

A test asserts the exact key set of `status` events, so the "safe fields only"
property cannot erode.

**A tool-using turn does not stream token-by-token.** It cannot: the model may
answer, call a tool, read the result, and answer again — only the last of those
is the reply. The `tool_status` events carry the progress instead, which is the
part of streaming that matters here. Tool-less turns stream as before.

---

## 8. Approval flow

Persisted in `action_approvals` (not in memory), created by the policy gate when
a YELLOW/RED call is attempted:

```
tool call → policy: PROMPT → approval row created (status pending)
          → loop reports APPROVAL_REQUIRED to the model and the UI
          → user approves / rejects via /api/v1/actions/{id}/approve|reject
```

**Status today:** the approval *record* and its API exist and are tested; no
YELLOW/RED executor is wired, so an approved action records the decision and
still does not execute. Resuming a paused tool call after approval is **not
implemented** — that lands with the first real YELLOW tool.

---

## 9. Audit

Every invocation writes a `tool_invocations` row — allowed, blocked, pending, or
failed. No migration was needed; the table already carried the right columns.

Recorded: user, run, agent, tool, arguments, tier, decision, status, reason,
output reference, error, timings.

**Arguments are redacted before persistence.** Keys matching a secret-shaped
list (`password`, `api_key`, `token`, …) are masked, and long values truncated —
an audit table is evidence, not a log sink.

---

## 10. Security properties

| Property | How it is enforced |
| --- | --- |
| No arbitrary code execution | The calculator parses with `ast.parse` and walks an **allowlist** of node types. Calls, names, attributes, and comprehensions are rejected at parse level — there is no sandbox to out-think. `eval` is never used. |
| No shell execution | No tool spawns a process. There is no shell tool. |
| Tenant isolation | `user_id` comes from `ToolContext`, built from the authenticated request. Tool arguments cannot widen it — a model asking for another user's data searches its own. |
| Prompt injection | Policy reads only code-defined state. Search results are marked `untrusted` and can never escalate a tier. |
| Resource exhaustion | Exponent cap, expression length cap, per-tool timeout, iteration cap, calls-per-step cap. |
| Secret leakage | Redaction before audit; internals never serialised into the model's tool schema. |

This is not theoretical. The first probe of a local model with tools attached,
asked only to say hello, produced `calculator(expression="print('Hello')")`. An
implementation built on `eval` would have run it. **A tool's safety cannot rest
on the model's good behaviour.**

---

## 11. Model support

Tool calling is an optional provider capability, `SupportsToolCalling`.

| Provider | Native tool calling | Verified |
| --- | --- | --- |
| Ollama `qwen2.5:3b` | ✅ | Calls tools, consumes results, stops correctly |
| Ollama `qwen3:8b` | ✅ | Same |
| OpenAI / Claude gateways | Not implemented | — |

A provider without the capability simply never receives tools, and the agent
answers from context. Selecting a non-tool model is a limitation, not an outage.

**Known model behaviour:** small models over-call when tools are present —
`qwen2.5:3b` reached for the calculator when asked to say hello. This is why
validation is strict, failures are structured, and tools are only offered to
agents that declare them.

---

## 12. Agent tool declarations

| Agent | Tools |
| --- | --- |
| `general`, `planner`, `memory` | calculator, current_time, memory_read, file_search, file_list |
| `career`, `learning`, `research` | the above **+ web_search** |
| `recall` | memory_read (deterministic; makes no model call) |

Declared in `manifests.py` via shared `_BASE_TOOLS` / `_RESEARCH_TOOLS` tuples, so
a capability change lands on every agent that should have it. A test asserts
every declared tool exists and sits within its agent's ceiling.

---

## 13. Adding a tool

1. Write `app/services/agents/tools/<name>.py` with
   `async def execute(context: ToolContext, args: dict) -> dict`.
   Raise on bad input; the executor converts it to a `FAILED` outcome.
2. Add a `ToolSpec` in `catalog.py` — key, description, JSON Schema, tier,
   timeout, executor.
3. Add the key to the agents that should have it in `manifests.py`.
4. Test: happy path, invalid arguments, and tenant isolation if it touches user
   data.

The orchestrator does not change.

---

## 14. Known limitations

- Approved YELLOW/RED actions record the decision but do not execute; resuming a
  paused call after approval is not implemented.
- Tool-using turns do not stream the reply token-by-token (§7).
- `doc_read` returns empty — the document store is a later phase.
- `web_search` returns `UNAVAILABLE` unless `TAVILY_API_KEY` and
  `AGENTS_WEB_SEARCH_ENABLED=true` are set. It deliberately does **not** fall
  back to the offline placeholder: doing so previously made the model relay mock
  rows to the user as real findings.
- No frontend approval buttons yet; `approval_required` surfaces in the activity
  trail only.
