/**
 * Discover GUMMY — content for the always-accessible "Discover" page.
 *
 * Data-driven sections. "Current Features" / "Future Features" render directly
 * from the capability registry, so they update automatically as capabilities
 * change status.
 */

import type { DiscoverSection } from "./types";

export const DISCOVER_SECTIONS: DiscoverSection[] = [
  {
    id: "what-is-gummy",
    title: "What is GUMMY?",
    body: [
      "GUMMY is your Personal AI Operating System — a unified layer for knowledge, goals, memory, learning, and execution.",
      "Unlike a chatbot, GUMMY remembers what matters, tracks your goals, and coordinates specialized agents on your behalf.",
    ],
  },
  {
    id: "current-features",
    title: "Current Features",
    body: ["What GUMMY can do today:"],
    showCapabilities: ["active"],
  },
  {
    id: "future-features",
    title: "Future Features",
    body: ["What's coming next:"],
    showCapabilities: ["coming-soon", "future"],
  },
  {
    id: "memory-system",
    title: "Memory System",
    body: [
      "GUMMY remembers important information across conversations — your profile, preferences, projects, and more.",
      "Every memory has provenance, importance, and confidence, and you stay in control: view, edit, or forget anything.",
    ],
  },
  {
    id: "agent-framework",
    title: "Agent Framework",
    body: [
      "Specialized agents collaborate to get work done, orchestrated and fully traceable.",
      "Each run records its steps and inter-agent messages, so you can always see how Gummy reached an answer.",
    ],
  },
  {
    id: "goals-and-tasks",
    title: "Goals & Tasks",
    body: [
      "Set long-term goals and let GUMMY break them into trackable tasks.",
      "Progress is persistent — your goals don't disappear when a conversation ends.",
    ],
  },
  {
    id: "privacy-and-security",
    title: "Privacy & Security",
    body: [
      "Your data is tenant-isolated and yours to control. Consequential actions require your approval.",
      "Actions are classified Green / Yellow / Red, and sensitive ones always ask first.",
    ],
  },
  {
    id: "product-roadmap",
    title: "Product Roadmap",
    body: [
      "More agents (Career, Learning, Research, and beyond), workflow learning, and N8N-powered automation are on the way — building toward a coordinated AI workforce.",
    ],
    showCapabilities: ["coming-soon", "future"],
  },
];
