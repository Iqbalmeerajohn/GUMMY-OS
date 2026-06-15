/**
 * Future Vision — the living roadmap inside GUMMY (data-driven).
 * Plain language, not marketing or architecture. Drives the /future experience.
 */

export interface VisionPillar {
  title: string;
  description: string;
}

export interface PlannedCapability {
  title: string;
  description: string;
}

export interface EvolutionStage {
  when: string;
  what: string;
}

/** Section 1 — completed milestones. */
export const COMPLETED_MILESTONES: string[] = [
  "Memory Engine",
  "Security & Auth",
  "Conversations Foundation",
  "Agent Framework",
  "Onboarding",
  "Dashboard",
];

/** Section 2 — what GUMMY is becoming (simple language). */
export const VISION_PILLARS: VisionPillar[] = [
  {
    title: "Memory",
    description: "GUMMY remembers what matters about you and your work.",
  },
  {
    title: "Goals",
    description: "It keeps track of what you're trying to achieve.",
  },
  {
    title: "Agents",
    description: "Specialists handle different kinds of work for you.",
  },
  {
    title: "Automation",
    description: "Repetitive work gets done for you, with your approval.",
  },
];

/** Section 3 — planned evolution (NOT "coming soon"). */
export const PLANNED_EVOLUTION: PlannedCapability[] = [
  {
    title: "Voice Interaction",
    description: "Talk naturally with GUMMY using voice and text.",
  },
  {
    title: "Workflow Learning",
    description: "Teach GUMMY how you work and let it learn your workflows.",
  },
  {
    title: "Content Agent",
    description: "Create and manage content across platforms.",
  },
  {
    title: "Research Agent",
    description: "Conduct deep research and organize findings.",
  },
  {
    title: "Career Agent",
    description: "Help with applications, interviews, and growth.",
  },
  {
    title: "Learning Agent",
    description: "Build personalized learning paths.",
  },
  {
    title: "Sales Agent",
    description: "Assist with sales workflows and follow-ups.",
  },
  {
    title: "Admin Agent",
    description: "Handle reporting and operational tasks.",
  },
  {
    title: "Business Agent",
    description: "Help run projects and business operations.",
  },
  {
    title: "Fitness Agent",
    description: "Support health goals and training plans.",
  },
  {
    title: "Tool Ecosystem",
    description: "Connect calendars, email, documents, and external services.",
  },
  {
    title: "N8N Automation Layer",
    description: "Turn instructions into automated workflows.",
  },
  {
    title: "Image Intelligence",
    description: "Generate, edit, organize, and manage visual assets.",
  },
  {
    title: "Video Intelligence",
    description: "Create short-form and long-form video content.",
  },
  {
    title: "AI Workforce",
    description: "Multiple specialized agents collaborating together.",
  },
];

/** Section 4 — the long-term vision. */
export const LONG_TERM_VISION =
  "Most AI systems answer questions. GUMMY is being designed to remember context, understand goals, coordinate agents, learn workflows, and help execute work over time.";

/** Section 5 — your future with GUMMY. */
export const EVOLUTION_STAGES: EvolutionStage[] = [
  { when: "Today", what: "Assistant" },
  { when: "Tomorrow", what: "Operating System" },
  { when: "Future", what: "Personal AI Team" },
];
