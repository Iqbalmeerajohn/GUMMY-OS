/**
 * GUMMY Feature Registry — the SINGLE SOURCE OF TRUTH for capabilities.
 *
 * Consumed by the Agent Directory panel and the shared status badge, so a
 * capability's status is stated in exactly one place. Statuses here mirror the
 * backend: an agent is "released" only if the router can actually reach it —
 * everything else carries "planned" so the directory never implies a capability
 * the server does not have.
 */

export type FeatureStatus =
  | "released"
  | "in-development"
  | "planned"
  | "researching";

export type FeatureCategory =
  | "core"
  | "agent"
  | "automation"
  | "voice"
  | "vision"
  | "video"
  | "workforce";

export interface Feature {
  id: string;
  title: string;
  description: string;
  status: FeatureStatus;
  category: FeatureCategory;
  /** Icon name resolved via lib/icons. */
  icon: string;
  /** ISO date; present for released features (drives the changelog order). */
  released_at?: string;
  /** Eligible to appear in the Explore GUMMY tour. */
  show_in_tour: boolean;
  /** Eligible to appear on the dashboard. */
  show_in_dashboard: boolean;
  /** Eligible for the "New in GUMMY" announcement popup. */
  show_popup: boolean;
  /** Optional dedicated route. */
  route?: string;
  /** Short planned-capability bullets (agents/roadmap cards). */
  highlights?: string[];
}

export const STATUS_LABEL: Record<FeatureStatus, string> = {
  released: "Released",
  "in-development": "In Development",
  planned: "Planned",
  researching: "Researching",
};

/** Tailwind classes per status (badge styling). */
export const STATUS_CLASS: Record<FeatureStatus, string> = {
  released: "bg-primary/15 text-primary border-primary/30",
  "in-development": "bg-amber-400/15 text-amber-300 border-amber-400/30",
  planned: "bg-muted text-muted-foreground border-border",
  researching: "bg-sky-400/15 text-sky-300 border-sky-400/30",
};

export const FEATURES: Feature[] = [
  // ── Core (released) ───────────────────────────────────────────────────────
  {
    id: "memory",
    title: "Memory",
    description: "GUMMY remembers what matters across conversations.",
    status: "released",
    category: "core",
    icon: "Brain",
    released_at: "2026-05-01",
    show_in_tour: true,
    show_in_dashboard: true,
    show_popup: false,
  },
  {
    id: "conversations",
    title: "Conversations",
    description: "Natural conversations with memory in the loop.",
    status: "released",
    category: "core",
    icon: "MessageSquare",
    released_at: "2026-05-15",
    show_in_tour: true,
    show_in_dashboard: false,
    show_popup: false,
  },
  {
    id: "search",
    title: "Search",
    description: "Search across conversations, memories, and goals.",
    status: "released",
    category: "core",
    icon: "Search",
    released_at: "2026-05-20",
    show_in_tour: true,
    show_in_dashboard: false,
    show_popup: false,
  },
  {
    id: "context",
    title: "Context Retrieval",
    description: "The right context, surfaced at the right moment.",
    status: "released",
    category: "core",
    icon: "FileText",
    released_at: "2026-05-22",
    show_in_tour: false,
    show_in_dashboard: false,
    show_popup: false,
  },
  {
    id: "goals",
    title: "Goals",
    description: "Turn long-term goals into tracked progress.",
    status: "released",
    category: "core",
    icon: "Target",
    released_at: "2026-06-01",
    show_in_tour: true,
    show_in_dashboard: true,
    show_popup: false,
  },
  {
    id: "agents",
    title: "Agents",
    description: "A framework for specialized agents to collaborate.",
    status: "released",
    category: "core",
    icon: "Workflow",
    released_at: "2026-06-05",
    show_in_tour: true,
    show_in_dashboard: true,
    show_popup: false,
  },
  {
    id: "security",
    title: "Security & Auth",
    description: "Private by default, with approvals for sensitive actions.",
    status: "released",
    category: "core",
    icon: "ShieldCheck",
    released_at: "2026-06-10",
    show_in_tour: false,
    show_in_dashboard: false,
    show_popup: false,
  },
  {
    id: "activity",
    title: "Activity Tracking",
    description: "A transparent record of what GUMMY does.",
    status: "released",
    category: "core",
    icon: "Activity",
    released_at: "2026-06-12",
    show_in_tour: false,
    show_in_dashboard: false,
    show_popup: false,
  },
  {
    id: "profiles",
    title: "User Profiles",
    description: "Your identity and preferences, remembered.",
    status: "released",
    category: "core",
    icon: "UserCircle",
    released_at: "2026-06-14",
    show_in_tour: false,
    show_in_dashboard: false,
    show_popup: false,
  },
  {
    id: "onboarding",
    title: "Onboarding",
    description: "A guided introduction to your operating system.",
    status: "released",
    category: "core",
    icon: "Rocket",
    released_at: "2026-06-14",
    show_in_tour: false,
    show_in_dashboard: false,
    show_popup: false,
  },
  {
    id: "command-center",
    title: "Command Center",
    description:
      "Your OS home — today's focus, agents, and capabilities at a glance.",
    status: "released",
    category: "core",
    icon: "LayoutDashboard",
    released_at: "2026-06-15",
    show_in_tour: true,
    show_in_dashboard: false,
    show_popup: true,
    route: "/dashboard",
  },

  // ── Agents ────────────────────────────────────────────────────────────────
  {
    id: "memory-agent",
    title: "Memory Agent",
    description: "Curates and recalls what matters about you.",
    status: "released",
    category: "agent",
    icon: "Brain",
    released_at: "2026-05-01",
    show_in_tour: false,
    show_in_dashboard: true,
    show_popup: false,
    highlights: ["Smart recall", "Provenance", "Consent controls"],
  },
  {
    id: "goal-agent",
    title: "Planner Agent",
    description: "Breaks goals into steps and tracks progress.",
    status: "released",
    released_at: "2026-06-10",
    category: "agent",
    icon: "Target",
    show_in_tour: false,
    show_in_dashboard: true,
    show_popup: false,
    highlights: ["Goal planning", "Progress tracking", "Nudges"],
  },
  {
    id: "workflow-agent",
    title: "Workflow Agent",
    description: "Learns how you work and automates the repetitive.",
    status: "planned",
    category: "agent",
    icon: "Workflow",
    show_in_tour: false,
    show_in_dashboard: true,
    show_popup: false,
    highlights: ["Workflow learning", "Automation", "Approvals"],
  },
  {
    id: "learning-agent",
    title: "Learning Agent",
    description: "Builds personalized learning paths.",
    status: "released",
    released_at: "2026-06-10",
    category: "agent",
    icon: "GraduationCap",
    show_in_tour: false,
    show_in_dashboard: true,
    show_popup: false,
    highlights: ["Curricula", "Spaced repetition", "Skill tracking"],
  },
  {
    id: "research-agent",
    title: "Research Agent",
    description: "Conducts deep research and organizes findings.",
    status: "released",
    released_at: "2026-06-24",
    category: "agent",
    icon: "Telescope",
    show_in_tour: false,
    show_in_dashboard: true,
    show_popup: false,
    highlights: ["Multi-step research", "Citations", "Summaries"],
  },
  {
    id: "career-agent",
    title: "Career Agent",
    description: "Helps with applications, interviews, and growth.",
    status: "released",
    released_at: "2026-06-10",
    category: "agent",
    icon: "Briefcase",
    show_in_tour: false,
    show_in_dashboard: true,
    show_popup: false,
    highlights: ["Resumes", "Interview prep", "Outreach"],
  },
  {
    id: "content-agent",
    title: "Content Agent",
    description: "Creates and manages content across platforms.",
    status: "planned",
    category: "agent",
    icon: "PenLine",
    show_in_tour: false,
    show_in_dashboard: false,
    show_popup: false,
    highlights: ["Drafting", "Editing", "Repurposing"],
  },
  {
    id: "marketing-agent",
    title: "Marketing Agent",
    description: "Plans and runs marketing workflows.",
    status: "planned",
    category: "agent",
    icon: "Megaphone",
    show_in_tour: false,
    show_in_dashboard: false,
    show_popup: false,
    highlights: ["Campaigns", "Scheduling", "Analytics"],
  },
  {
    id: "sales-agent",
    title: "Sales Agent",
    description: "Assists with sales workflows and follow-ups.",
    status: "planned",
    category: "agent",
    icon: "TrendingUp",
    show_in_tour: false,
    show_in_dashboard: false,
    show_popup: false,
    highlights: ["Pipeline", "Outreach", "Follow-ups"],
  },
  {
    id: "business-agent",
    title: "Business Agent",
    description: "Helps run projects and business operations.",
    status: "planned",
    category: "agent",
    icon: "Building2",
    show_in_tour: false,
    show_in_dashboard: false,
    show_popup: false,
    highlights: ["Planning", "Operations", "Decisions"],
  },
  {
    id: "admin-agent",
    title: "Admin Agent",
    description: "Handles reporting and operational tasks.",
    status: "planned",
    category: "agent",
    icon: "CalendarClock",
    show_in_tour: false,
    show_in_dashboard: false,
    show_popup: false,
    highlights: ["Scheduling", "Reporting", "Inbox"],
  },
  {
    id: "fitness-agent",
    title: "Fitness Agent",
    description: "Supports health goals and training plans.",
    status: "planned",
    category: "agent",
    icon: "Dumbbell",
    show_in_tour: false,
    show_in_dashboard: false,
    show_popup: false,
    highlights: ["Training plans", "Habits", "Progress"],
  },
  {
    id: "media-agent",
    title: "Media Agent",
    description: "Generates and manages images and video.",
    status: "researching",
    category: "agent",
    icon: "Clapperboard",
    show_in_tour: false,
    show_in_dashboard: false,
    show_popup: false,
    highlights: ["Image generation", "Video creation", "Asset management"],
  },

  // ── Capabilities (roadmap) ────────────────────────────────────────────────
  {
    id: "automation",
    title: "Automation",
    description: "Automate multi-step work with approval gates.",
    status: "in-development",
    category: "automation",
    icon: "Zap",
    show_in_tour: true,
    show_in_dashboard: true,
    show_popup: false,
    route: "/automation",
  },
  {
    id: "voice",
    title: "Voice",
    description: "Talk naturally with GUMMY using voice and text.",
    status: "researching",
    category: "voice",
    icon: "Mic",
    show_in_tour: true,
    show_in_dashboard: true,
    show_popup: false,
    route: "/voice",
  },
  {
    id: "vision",
    title: "Vision",
    description: "Generate, edit, and understand visual assets.",
    status: "researching",
    category: "vision",
    icon: "Image",
    show_in_tour: false,
    show_in_dashboard: true,
    show_popup: false,
  },
  {
    id: "video",
    title: "Video",
    description: "Create short-form and long-form video content.",
    status: "researching",
    category: "video",
    icon: "Video",
    show_in_tour: false,
    show_in_dashboard: true,
    show_popup: false,
  },
  {
    id: "workflow-learning",
    title: "Workflow Learning",
    description: "Teach GUMMY how you work and let it learn your workflows.",
    status: "researching",
    category: "automation",
    icon: "Sparkles",
    show_in_tour: true,
    show_in_dashboard: true,
    show_popup: false,
  },
  {
    id: "n8n",
    title: "N8N Integration",
    description: "Turn instructions into automated workflows.",
    status: "planned",
    category: "automation",
    icon: "Plug",
    show_in_tour: false,
    show_in_dashboard: false,
    show_popup: false,
  },
  {
    id: "browser-automation",
    title: "Browser Automation",
    description: "Let GUMMY operate the web on your behalf, safely.",
    status: "researching",
    category: "automation",
    icon: "Globe",
    show_in_tour: false,
    show_in_dashboard: false,
    show_popup: false,
  },
  {
    id: "ai-workforce",
    title: "AI Workforce",
    description: "Multiple specialized agents collaborating together.",
    status: "planned",
    category: "workforce",
    icon: "Users",
    show_in_tour: true,
    show_in_dashboard: true,
    show_popup: false,
  },
];

// ── Selectors ───────────────────────────────────────────────────────────────

export function getFeatures(): Feature[] {
  return FEATURES;
}

export function getByStatus(status: FeatureStatus): Feature[] {
  return FEATURES.filter((f) => f.status === status);
}

export function getAgents(): Feature[] {
  // Live agents first: the directory should read as "here is what answers you
  // today", with the plan phase below it rather than mixed through it.
  return FEATURES.filter((f) => f.category === "agent").sort(
    (a, b) =>
      Number(b.status === "released") - Number(a.status === "released"),
  );
}

/** Released features, newest first (the changelog timeline). */
export function getReleased(): Feature[] {
  return FEATURES.filter((f) => f.status === "released" && f.released_at).sort(
    (a, b) => (a.released_at! < b.released_at! ? 1 : -1),
  );
}

/** Curated capability map (#1) in display order. */
const CAPABILITY_MAP_IDS = [
  "memory",
  "goals",
  "agents",
  "automation",
  "voice",
  "vision",
  "video",
  "workflow-learning",
  "ai-workforce",
];
export function getCapabilityMap(): Feature[] {
  return CAPABILITY_MAP_IDS.map(
    (id) => FEATURES.find((f) => f.id === id)!,
  ).filter(Boolean);
}

/** Active-agents strip on the dashboard (#1). */
const ACTIVE_AGENT_IDS = [
  "memory-agent",
  "learning-agent",
  "research-agent",
  "career-agent",
  "goal-agent",
  "workflow-agent",
];
export function getActiveAgents(): Feature[] {
  return ACTIVE_AGENT_IDS.map(
    (id) => FEATURES.find((f) => f.id === id)!,
  ).filter(Boolean);
}

/** Features eligible for the Explore GUMMY tour. */
export function getTourFeatures(): Feature[] {
  return FEATURES.filter((f) => f.show_in_tour);
}

/** The newest popup-eligible release (drives the What's New announcement). */
export function getLatestAnnouncement(): Feature | null {
  const popups = FEATURES.filter(
    (f) => f.status === "released" && f.show_popup && f.released_at,
  ).sort((a, b) => (a.released_at! < b.released_at! ? 1 : -1));
  return popups[0] ?? null;
}

/** Agent status reads "Available" when released, else the standard label. */
export function agentStatusLabel(status: FeatureStatus): string {
  return status === "released" ? "Available" : STATUS_LABEL[status];
}

// ── Narrative (Future Vision copy — not a feature list) ───────────────────────

export const VISION_PILLARS = [
  { title: "Memory", description: "GUMMY remembers what matters about you." },
  { title: "Goals", description: "It keeps track of what you're achieving." },
  {
    title: "Agents",
    description: "Specialists handle different kinds of work.",
  },
  {
    title: "Automation",
    description: "Repetitive work gets done, with your approval.",
  },
];

export const LONG_TERM_VISION =
  "Most AI systems answer questions. GUMMY is being designed to remember context, understand goals, coordinate agents, learn workflows, and help execute work over time.";

export const EVOLUTION_STAGES = [
  { when: "Today", what: "Assistant" },
  { when: "Tomorrow", what: "Operating System" },
  { when: "Future", what: "Personal AI Team" },
];
