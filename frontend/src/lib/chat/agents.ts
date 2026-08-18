/**
 * The M8 multi-agent workforce — the specialists the backend Router selects and
 * the workspace selector can pin manually. ``value`` is the backend agent key
 * (sent as `agent` on a turn to override Auto routing); ``label`` is the badge
 * text. "General" is the always-on fallback and is not a manual specialist here
 * (Auto already falls back to it), so it is not listed as a selectable override.
 */
export const AGENTS = [
  { value: "career", label: "Career" },
  { value: "learning", label: "Learning" },
  { value: "planner", label: "Planner" },
  { value: "memory", label: "Memory" },
  { value: "research", label: "Research" },
  { value: "automation", label: "Automation" },
] as const;

/** Backend agent key → human label (badges). Includes the General fallback. */
export const AGENT_LABELS: Record<string, string> = {
  general: "General",
  career: "Career",
  learning: "Learning",
  planner: "Planner",
  memory: "Memory",
  research: "Research",
  automation: "Automation",
  recall: "Recall",
};
