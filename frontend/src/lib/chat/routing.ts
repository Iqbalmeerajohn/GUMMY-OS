/**
 * Agent mode (Auto + manual override) and a lightweight client-side routing
 * PREVIEW.
 *
 * GUMMY's production principle: the user shouldn't have to pick an agent — the
 * backend Router selects the right specialist from the message, memory, goals,
 * and files. This module powers the selector, the manual override, and the
 * pre-reply "likely agent" preview. The keyword heuristic here is a PREVIEW
 * only; the real decision is the backend's and is surfaced on each reply (the
 * stream's `agent` field / the message's `metadata.agent_key`).
 */

import { AGENTS } from "./agents";

export const AUTO = "auto";

/** Selector options: Auto (default) + the five manual specialists. */
export const AGENT_MODES = [{ value: AUTO, label: "Auto" }, ...AGENTS] as const;

/**
 * Map a selector mode to the backend `agent` override sent on a turn. Auto
 * returns `undefined` (no override → the Router decides).
 */
export function modeToAgent(mode: string): string | undefined {
  return mode === AUTO ? undefined : mode;
}

/**
 * Map a selector mode to a valid conversation `agent_context` (thread hub) for
 * conversation creation. The hub enum is general/career/learning/research/
 * builder, so Auto and the planner/memory specialists collapse to "general".
 */
const CONTEXT_MODES = new Set(["career", "learning", "research", "builder"]);
export function modeToAgentContext(mode: string): string {
  return CONTEXT_MODES.has(mode) ? mode : "general";
}

// Preview keyword rules — must stay roughly aligned with the backend manifests
// (services/agents/manifests.py). Preview only; never drives backend routing.
const RULES: { label: string; keywords: string[] }[] = [
  {
    label: "Career",
    keywords: [
      "job",
      "resume",
      "cv",
      "career",
      "interview",
      "internship",
      "application",
      "linkedin",
      "salary",
      "hiring",
    ],
  },
  {
    label: "Learning",
    keywords: [
      "teach",
      "learn",
      "study",
      "course",
      "explain",
      "tutorial",
      "concept",
      "curriculum",
    ],
  },
  {
    label: "Planner",
    keywords: [
      "goal",
      "milestone",
      "timeline",
      "plan",
      "schedule",
      "deadline",
      "roadmap",
    ],
  },
  {
    label: "Memory",
    keywords: [
      "remember",
      "memory",
      "memories",
      "recall",
      "history",
      "profile",
    ],
  },
  {
    label: "Research",
    keywords: [
      "research",
      "compare",
      "analyze",
      "investigate",
      "market",
      "trend",
      "vs",
    ],
  },
];

/** Preview which agent GUMMY would likely engage (Auto), or the pinned one. */
export function previewRoutedAgents(text: string, mode: string): string[] {
  if (mode !== AUTO) {
    return [AGENT_MODES.find((m) => m.value === mode)?.label ?? "General"];
  }
  const lower = text.toLowerCase();
  const hits = RULES.filter((r) =>
    r.keywords.some((k) => lower.includes(k)),
  ).map((r) => r.label);
  return hits.length > 0 ? hits.slice(0, 1) : ["General"];
}

/**
 * Active agent + a human-readable reason for the transparency layer. Preview
 * only — the authoritative agent is the backend's, shown on the reply.
 */
export function routedAgentsWithReason(
  text: string,
  mode: string,
): { agents: string[]; reason: string } {
  const agents = previewRoutedAgents(text, mode);
  if (mode !== AUTO) {
    return { agents, reason: "Manual agent selection." };
  }
  const lower = text.toLowerCase();
  const matched = RULES.find((r) => r.keywords.some((k) => lower.includes(k)));
  const reason = matched
    ? `Looks like a ${matched.label.toLowerCase()} request.`
    : "General request — no specialized agent needed.";
  return { agents, reason };
}
