# Multi-Agent Delegation

How one request becomes several agents, and — more often — how it stays one.

This describes what exists today. Anything not implemented is marked as such.

---

## 1. The problem

The orchestrator's pipeline machinery, A2A tracing, and scratch hand-off were
all built and tested. But nothing produced a multi-agent plan: `score_agents`
collapsed every request to its single highest-scoring specialist. So

> "Find AI jobs for me and then create a learning plan for the biggest gap"

ran Career and silently dropped the second half of the sentence.

---

## 2. Detection is grammatical, not statistical

The hard part is not spotting two capabilities — it is **refusing to spot two
when there is only one**.

| Request | Career kw | Learning kw | Tasks |
| --- | --- | --- | --- |
| "find AI/ML fresher **jobs** and **internships**" | 4 | 0 | **one** |
| "find **jobs** and then build a **learning** plan" | 1 | 2 | **two** |

Counting keywords cannot separate those. Grammar can. So a request only fans
out when a **connective** separates clauses that resolve to **different**
specialists:

```
" and then " · " then " · " and after that " · ", and " · " and also "
" and " · ";" · ","
```

**A request with no connective can never become multi-agent.** That is the
safety property: the default is always single-agent.

### Three conditions, all required

1. the request splits into **two or more clauses**;
2. at least **two clauses resolve to specialists**;
3. those specialists are **not all the same agent**.

Condition 3 is what collapses *"jobs and internships"* back to one step. It is
also why a bare comma is safe as a separator: *"AI jobs in Bangalore, Chennai,
or Pune"* splits into three clauses, yields one specialist, and collapses
straight back to `single`.

Consecutive duplicates **fold** rather than dedupe globally, so a genuine
A → B → A shape stays expressible. A clause with no specialist (*"tell me how I
should prepare"*) is folded into the previous step's intent rather than dropped,
so its wording still reaches an agent. Clause order is execution order. Capped
at `COMPOUND_MAX_STEPS` (3).

### Where it sits in routing

```
manual override      → that agent, single          (user's explicit instruction)
agent_context hint   → recall → general pipeline
COMPOUND DETECTION   → pipeline of specialists     ← new
keyword scoring      → best single specialist
LLM fallback         → opt-in, off by default
low confidence       → general
```

Compound is checked **before** single scoring, because single scoring collapses
the request to its highest scorer and would discard the second task.

---

## 2b. Choosing the shape

`plan_compound` splits a request on connectives, resolves each clause to a
specialist, and then decides between two multi-agent shapes.

```
                     two or more clauses,
                     two distinct specialists
                              |
              does a later clause need an earlier result?
                     /                                          yes                          no
                   |                            |
               PIPELINE                     PARALLEL
           (findings handed              (asyncio.gather,
            forward, in order)            then synthesis)
```

**Dependency is signalled two ways.** A sequencing connective — `and then`,
`after that`, `then also` — states the order outright. Otherwise a
back-reference in the later clause does: `based on`, `using the results`,
`those`, `them`, `for my biggest ...`, or a definite article on a
result-shaped noun (`research **the companies**`).

The definite-article rule requires the noun to follow `the` immediately, which
is what keeps it narrow: *"research **the latest AI agent companies**"*
introduces its own subject and stays independent.

**PIPELINE is the default of the two.** Running independent work sequentially
costs latency. Running dependent work concurrently means the second agent
answers without the information it was supposed to receive — a wrong answer,
not a slow one. Independence has to be demonstrated, never assumed.

`SINGLE` remains the default overall: a request that does not split, or whose
clauses all resolve to the same specialist, never fans out. *"Find AI/ML jobs
and internships"* is one task phrased twice.

## 2c. Synthesis, and what happens when a branch fails

Parallel branches produce two independent answers. Stacking them is a
transcript of how the work was divided, not an answer, so
`synthesis.synthesize_parallel` writes one reply from them. Its prompt carries
the branch outputs and nothing else, and forbids naming agents or adding
findings.

Synthesis is an improvement, never a dependency: any failure — no provider, an
exception, or a suspiciously short generation — falls back to
`compose.merge_parallel`, which is deterministic. Losing synthesis costs prose,
never content.

A branch that fails is **named**, not dropped:

```
Found 3 fresher roles at X, Y, Z.

I couldn't complete the research this time, so that part is missing.
```

Silence is the dangerous option here: a parallel run that quietly discards a
failed branch reads as a complete answer to a half-answered question. The raw
exception is not shown — it is already on the step record.

## 3. Structured hand-off

Grounding previously read only a `digest` key — which the deterministic recall
agent produces and specialists never do. So even when a pipeline ran, the second
agent's prompt contained **no trace of the first**, and it answered as though
the earlier step had never happened. Nothing produced pipelines, so nothing
exposed it.

```python
AgentHandoff(
    source_agent="career",
    target_agent="learning",
    purpose="career_to_learning",
    relevant_findings=["Missing skill: LangGraph", "Target role: AI Engineer"],
    recommended_next_action="Use these findings to answer the part that is yours.",
)
```

**Findings are extracted structurally**, not by a model call. The agents are
already instructed to answer in headings and bullets, so the bullets *are* the
conclusions; asking a model to summarise text it just wrote would add a full
generation to every pipeline step. Prose replies fall back to leading sentences.

Bounded at **6 findings × 220 chars**. A pipeline step is a summary, not a
transcript — pasting whole replies forward is how a three-step chain runs out
of context.

Grounding accepts both shapes, so the recall `digest` path is untouched.

**Nothing that crosses an agent boundary is chain-of-thought.** Findings are
conclusions and a next action.

---

## 4. Execution

Reuses `_run_sequential` unchanged. Each step:

```
open_step → task hop → dispatch (with its own tool loop) → close_step
          → result hop → build handoff → append to scratch
```

Every agent keeps **its own tool ceiling**, however it is reached. Delegation
never widens capability: Automation has no web access when reached via a
pipeline, and Career cannot create automations.

**Parallel execution** is now routed as well as implemented. Historically
`_run_parallel` existed (branch-isolated failures) but
the router does not currently produce a `PARALLEL` plan from keywords — see §8.

---

## 5. Synthesis

For `single` and `pipeline`, the **terminal agent is the synthesiser**. Because
it receives the upstream findings in its prompt, its answer already
incorporates them — so the user gets one coherent reply rather than two
concatenated ones. `compose_reply` returns that terminal reply unchanged.

`parallel` has no terminal agent — its branches are peers — so it gets an
explicit synthesis pass instead. See §2c.

---

## 6. Trace

`GET /api/v1/runs?conversation_id=…` and `GET /api/v1/runs/{id}` expose the run,
its steps, its A2A hops, and its tool invocations.

**Read-only.** A trace is evidence; only the orchestrator may write one.
Tenant-scoped — another tenant's run id returns **404, not 403**, because the
existence of an id is itself information. Payloads are the previews already
stored: intents and reply excerpts, never prompts and never reasoning.

Verified live for a Career → Learning turn:

```
steps: [('career','succeeded'), ('learning','succeeded')]
hops:  [('orchestrator','career','task'), ('career',None,'result'),
        ('orchestrator','learning','task'), ('learning',None,'result')]
```

---

## 7. Verified behaviour

Live, Postgres + Ollama over HTTP — **19/19**. The persisted `route_plan` is the
authority, not the stream.

**Stays single** (regression guard):

| Request | Plan |
| --- | --- |
| "Find AI/ML fresher opportunities suitable for me." | `single [career]` |
| "Teach me LangGraph from beginner to advanced." | `single [learning]` |
| "Research the AI agent landscape." | `single [research]` |
| "Remind me tomorrow at 9 AM to review my goals." | `single [automation]` |
| "Find AI/ML fresher jobs and internships" | `single [career]` |
| "Find me AI jobs in Bangalore, Chennai, or Pune" | `single [career]` |
| "Remind me tomorrow to study LangGraph" | `single [automation]` |
| "what is the capital of France" | `single [general]` |

**Fans out:**

| Request | Plan |
| --- | --- |
| "Find AI/ML fresher jobs … and create a learning plan for the biggest skill gap." | `pipeline [career, learning]` |
| "Research LangGraph and then teach me the most important concepts." | `pipeline [research, learning]` |
| "Find suitable AI jobs, research the companies, and tell me how I should prepare." | `pipeline [career, research]` |

### Latency (local, `qwen2.5:3b`)

| Shape | Observed |
| --- | --- |
| Single agent | 7.7 – 14.0 s |
| Two-agent pipeline | 17.3 – 22.5 s |
| Two-agent + tools | 30.4 s |

A pipeline costs roughly one extra agent turn — as expected, since each step is
a full grounded generation. No optimisation attempted.

---

## 8. Limitations

- **Same-specialist fan-out is not expressible.** *"Research these three
  companies and compare them"* resolves every clause to Research, so it
  collapses to a single turn rather than three parallel branches. Parallel
  requires two *distinct* specialists (see §2b).
- **Detection is English-only** and connective-based. A compound request phrased
  without a connective ("find jobs — build me a plan") stays single-agent. That
  is the conservative failure direction.
- **Three steps maximum.**
- **No cross-step retry.** A failing step aborts the pipeline and `run_turn`'s
  fallback answers, so the user still gets a reply, but upstream findings from
  the completed step are not preserved into that fallback.
- **Career → Automation** ("find me AI jobs every Monday and remind me") is not
  implemented as a recurring search. Automation can schedule a reminder; it
  cannot schedule a *search*, and the agent says so rather than pretending.
- **No LangGraph.** Deliberately — this architecture is proven first.

---

## 9. Security

| Property | How |
| --- | --- |
| Tool ceilings across a pipeline | Read per-step from the agent's manifest via the registry; a caller cannot widen them |
| Tenant isolation | Every repository call is user-scoped; trace reads 404 for another tenant |
| No reasoning in traces | Hop payloads are previews (`intent_preview`, `reply_preview`, output *keys*); asserted by test |
| No reasoning to the client | Only `status` / `tool_status` events, carrying a stage, an agent key, and a label |
| Memory stays relevance-gated | Unchanged; the 0.45 semantic floor applies to every agent in a pipeline |
| Bounded fan-out | `COMPOUND_MAX_STEPS`, plus the orchestrator's existing step and token caps |
