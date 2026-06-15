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
    id: "explore",
    title: "Explore GUMMY",
    description: "See new releases, capabilities, and roadmap progress.",
    icon: "Compass",
    href: "/onboarding",
  },
  {
    id: "first-memory",
    title: "Teach GUMMY something",
    description: "Tell GUMMY a fact to remember about you.",
    icon: "Brain",
    href: "/workspace?prompt=Remember%20that%20",
  },
  {
    id: "open-workspace",
    title: "Open the Workspace",
    description: "Converse and co-work with GUMMY and your agents.",
    icon: "MessageSquare",
    href: "/workspace",
  },
];

export const QUICK_START_SUGGESTIONS: string[] = [
  "What can you help me with?",
  "Remember that I prefer concise answers",
  "Help me plan my week",
  "What do you know about me?",
];
