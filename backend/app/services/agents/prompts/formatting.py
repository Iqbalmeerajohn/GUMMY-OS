"""Shared response-formatting rules for the M8 specialists (M8 Polish, A1).

One directive, prepended once to every specialist's system prompt by the shared
handler (``handlers/specialist_agent.py``). It bans markdown tables — which
render badly in the chat stream — and replaces them with plain, stream-safe
structures (comparison blocks, roadmaps, learning/career plans, research
summaries). Identity/voice stays per-agent in each persona builder; *formatting*
is cross-cutting and lives here so all five specialists stay consistent (Rule
#2/#5: one injection point, no per-persona duplication).

Pure text — no I/O, no state.
"""

from __future__ import annotations

# The single shared formatting contract. Kept terse: it is prepended to every
# specialist prompt, so every token here is paid on every specialist turn.
FORMATTING_RULES = (
    "Formatting rules (follow exactly):\n"
    "- NEVER output markdown tables (no `|` columns). They render badly in chat. "
    "Use the plain structures below instead.\n"
    "- Use short headers and bullet points; keep lines tight.\n"
    "\n"
    "When you COMPARE two or more things, use a Comparison Block — one labeled "
    "group per option, each with its own bullets:\n"
    "AI Engineer\n"
    "- point\n"
    "- point\n"
    "\n"
    "Data Engineer\n"
    "- point\n"
    "- point\n"
    "\n"
    "When you give a ROADMAP, use ordered phases:\n"
    "Phase 1 — <name>\n"
    "- step\n"
    "Phase 2 — <name>\n"
    "- step\n"
    "\n"
    "When you give a LEARNING PLAN, for each item give: Topic, Why it matters, "
    "Next action.\n"
    "\n"
    "When you give a CAREER PLAN, structure it as: Current State, Gap Analysis, "
    "Action Plan, Timeline.\n"
    "\n"
    "When you give a RESEARCH SUMMARY, structure it as: Summary, Key Findings, "
    "Recommendations."
)
