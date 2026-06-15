/**
 * Welcome Dashboard content — data-driven recommended actions + quick starts.
 * Feature routes (chat/memory/goals) land in M3+; until then non-routed items
 * are flagged `soon` and handled gracefully by the UI.
 */

export interface RecommendedAction {
  id: string;
  title: string;
  description: string;
  icon: string; // lucide icon name
  href?: string;
  soon?: boolean;
}

export const RECOMMENDED_ACTIONS: RecommendedAction[] = [
  {
    id: "tour",
    title: "Take the tour",
    description: "See what GUMMY can do and where it's headed.",
    icon: "Compass",
    href: "/onboarding",
  },
  {
    id: "first-memory",
    title: "Teach GUMMY something",
    description: "Tell GUMMY a fact to remember about you.",
    icon: "Brain",
    soon: true,
  },
  {
    id: "first-goal",
    title: "Set your first goal",
    description: "Turn an outcome you want into tracked progress.",
    icon: "Target",
    soon: true,
  },
];

export const QUICK_START_SUGGESTIONS: string[] = [
  "What can you help me with?",
  "Remember that I prefer concise answers",
  "Help me plan my week",
  "What do you know about me?",
];
