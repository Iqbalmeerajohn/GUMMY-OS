/**
 * Onboarding journey content — data-driven (7 guided screens).
 *
 * Copy lives here; each step maps to a visual component by `visual` key in the
 * OnboardingFlow. Keeps the experience editable without touching component code.
 */

export type OnboardingVisual =
  | "awaken"
  | "memory"
  | "agents"
  | "goals"
  | "ecosystem"
  | "roadmap-current"
  | "roadmap-future";

export interface OnboardingItem {
  title: string;
  desc?: string;
}

export interface OnboardingStep {
  id: string;
  kicker?: string;
  headline: string;
  /** Optional second headline line, emphasized in the accent color. */
  highlight?: string;
  paragraphs: string[];
  items?: OnboardingItem[];
  cta: string;
  visual: OnboardingVisual;
}

export const ONBOARDING_STEPS: OnboardingStep[] = [
  {
    id: "welcome",
    headline: "Welcome to GUMMY",
    highlight: "Your personal AI operating system.",
    paragraphs: [
      "The first system designed to remember, learn, organize, and help you achieve your goals over time.",
    ],
    cta: "Continue",
    visual: "awaken",
  },
  {
    id: "memory",
    headline: "Most AI tools forget.",
    highlight: "GUMMY remembers.",
    paragraphs: [
      "When you talk to most AI tools, every conversation starts from zero.",
      "GUMMY is different. It remembers what matters, learns your preferences, and builds context over time — so you never repeat yourself.",
    ],
    cta: "Next",
    visual: "memory",
  },
  {
    id: "agents",
    headline: "GUMMY is more than one AI.",
    paragraphs: [
      "Behind the scenes, specialized agents can work together.",
      "Instead of one assistant doing everything, GUMMY grows into a team that helps you get things done.",
    ],
    items: [
      { title: "Research" },
      { title: "Learning" },
      { title: "Career" },
      { title: "Content" },
      { title: "Planning" },
      { title: "Automation" },
    ],
    cta: "Next",
    visual: "agents",
  },
  {
    id: "goals",
    headline: "Turn goals into progress.",
    paragraphs: [
      "Most AI tools answer questions. GUMMY is being built to help you achieve outcomes.",
    ],
    items: [
      { title: "Track goals" },
      { title: "Remember progress" },
      { title: "Learn workflows" },
      { title: "Automate repetitive work" },
    ],
    cta: "Next",
    visual: "goals",
  },
  {
    id: "connect",
    headline: "Connect your tools.",
    paragraphs: [
      "Soon, GUMMY will connect with the tools, apps, and workflows you already use.",
      "The vision is simple: tell GUMMY what you want done, and let GUMMY coordinate the work.",
    ],
    items: [
      { title: "N8N" },
      { title: "Calendars" },
      { title: "Documents" },
      { title: "Knowledge bases" },
      { title: "Automations" },
    ],
    cta: "Next",
    visual: "ecosystem",
  },
  {
    id: "today",
    kicker: "Live now",
    headline: "Where GUMMY is today",
    paragraphs: ["The foundation is already running."],
    items: [
      { title: "Memory Engine" },
      { title: "Conversations" },
      { title: "Search" },
      { title: "Context Retrieval" },
      { title: "User Profiles" },
      { title: "Activity Tracking" },
    ],
    cta: "See What's Coming",
    visual: "roadmap-current",
  },
  {
    id: "next",
    kicker: "The roadmap",
    headline: "What comes next",
    paragraphs: ["GUMMY is growing into a coordinated AI workforce."],
    items: [
      { title: "Career Agent", desc: "Jobs, applications, and interviews." },
      { title: "Learning Agent", desc: "Personalized learning paths." },
      { title: "Research Agent", desc: "Finds, organizes, and summarizes." },
      { title: "Content Agent", desc: "Creates content and marketing assets." },
      { title: "Sales Agent", desc: "Supports business workflows." },
      { title: "Admin Agent", desc: "Operations and reporting." },
      {
        title: "Workflow Automation",
        desc: "Connects systems and executes tasks.",
      },
      {
        title: "AI Workforce",
        desc: "Multiple agents collaborating together.",
      },
    ],
    cta: "Enter GUMMY",
    visual: "roadmap-future",
  },
];
