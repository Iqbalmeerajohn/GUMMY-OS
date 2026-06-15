/**
 * Agent mode + a lightweight client-side routing PREVIEW.
 *
 * GUMMY's production principle: the user shouldn't pick an agent — GUMMY selects
 * the right agents from context, memory, goals, files, and intent (the backend
 * orchestrator does the real routing). This module powers the UI transparency
 * ("Active Agents") and the manual override. The keyword heuristic here is a
 * preview only; it does not drive backend behavior.
 */

import { AGENT_CONTEXTS } from "./agents";

export const AUTO = "auto";

/** Selector options: Auto (default) + manual contexts (testing / power users). */
export const AGENT_MODES = [
  { value: AUTO, label: "Auto" },
  ...AGENT_CONTEXTS,
] as const;

/** Map a UI mode to a backend agent_context (Auto → general; server routes). */
export function modeToAgentContext(mode: string): string {
  return mode === AUTO ? "general" : mode;
}

const RULES: { label: string; keywords: string[] }[] = [
  {
    label: "Career",
    keywords: ["job", "resume", "career", "interview", "application", "hiring"],
  },
  {
    label: "Research",
    keywords: [
      "research",
      "find",
      "sources",
      "summarize",
      "investigate",
      "compare",
    ],
  },
  {
    label: "Learning",
    keywords: ["learn", "study", "course", "curriculum", "practice", "explain"],
  },
  {
    label: "Builder",
    keywords: ["build", "code", "software", "app", "bug", "deploy", "api"],
  },
  {
    label: "Content",
    keywords: ["content", "write", "post", "blog", "caption", "draft"],
  },
  {
    label: "Sales",
    keywords: ["sale", "lead", "pipeline", "outreach", "follow up", "prospect"],
  },
  {
    label: "Admin",
    keywords: ["schedule", "admin", "report", "calendar", "email", "invoice"],
  },
];

/** Preview which agents GUMMY would likely engage for this turn. */
export function previewRoutedAgents(text: string, mode: string): string[] {
  if (mode !== AUTO) {
    return [AGENT_MODES.find((m) => m.value === mode)?.label ?? "General"];
  }
  const lower = text.toLowerCase();
  const hits = RULES.filter((r) =>
    r.keywords.some((k) => lower.includes(k)),
  ).map((r) => r.label);
  return hits.length > 0 ? hits.slice(0, 3) : ["General"];
}
