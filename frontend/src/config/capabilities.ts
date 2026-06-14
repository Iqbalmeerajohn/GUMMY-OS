/**
 * Capability registry — the single source of truth for what GUMMY can do.
 *
 * The UI (onboarding cards, capability grid, Discover page) renders from this
 * list. Adding a new agent or feature = add an entry here; promoting it from
 * "coming-soon" to "active" = change `status` + set `href`. No screen changes.
 *
 * Active capabilities map to shipped Phase 1–3 backend APIs. Coming-soon /
 * future entries align with the multi-agent + automation roadmap.
 */

import type { Capability } from "./types";

export const CAPABILITIES: Capability[] = [
  // ── Active (shipped backend, Phase 1–3) ──────────────────────────────────
  {
    id: "chat",
    name: "Chat",
    description: "Converse and co-work with Gummy, with memory in the loop.",
    status: "active",
    category: "core",
    icon: "MessageSquare",
    href: "/chat",
    order: 1,
  },
  {
    id: "memory",
    name: "Memory System",
    description: "Remembers important information across conversations.",
    status: "active",
    category: "core",
    icon: "Brain",
    href: "/memory",
    order: 2,
  },
  {
    id: "goals",
    name: "Goals System",
    description: "Tracks long-term goals and progress over time.",
    status: "active",
    category: "core",
    icon: "Target",
    href: "/goals",
    order: 3,
  },
  {
    id: "tasks",
    name: "Tasks",
    description: "Breaks goals into trackable units of work.",
    status: "active",
    category: "core",
    icon: "ListChecks",
    href: "/goals",
    order: 4,
  },
  {
    id: "search",
    name: "Search & Knowledge",
    description:
      "Search conversations, memories, goals, and future workspaces.",
    status: "active",
    category: "core",
    icon: "Search",
    href: "/search",
    order: 5,
  },
  {
    id: "agent-framework",
    name: "Multi-Agent Intelligence",
    description: "Specialized agents working together, with full traceability.",
    status: "active",
    category: "core",
    icon: "Workflow",
    href: "/activity",
    order: 6,
  },

  // ── Coming soon (roadmap agents) ─────────────────────────────────────────
  {
    id: "career-agent",
    name: "Career Agent",
    description: "Resumes, applications, interview prep, and outreach.",
    status: "coming-soon",
    category: "agent",
    icon: "Briefcase",
    order: 10,
  },
  {
    id: "learning-agent",
    name: "Learning Agent",
    description: "Curricula, spaced repetition, and skill progress.",
    status: "coming-soon",
    category: "agent",
    icon: "GraduationCap",
    order: 11,
  },
  {
    id: "research-agent",
    name: "Research Agent",
    description: "Multi-step research with cited, credible sources.",
    status: "coming-soon",
    category: "agent",
    icon: "Telescope",
    order: 12,
  },
  {
    id: "content-agent",
    name: "Content Agent",
    description: "Drafts, edits, and repurposes content across formats.",
    status: "coming-soon",
    category: "agent",
    icon: "PenLine",
    order: 13,
  },
  {
    id: "sales-agent",
    name: "Sales Agent",
    description: "Pipeline, outreach, and follow-up assistance.",
    status: "coming-soon",
    category: "agent",
    icon: "TrendingUp",
    order: 14,
  },
  {
    id: "business-agent",
    name: "Business Agent",
    description: "Operations, planning, and decision support.",
    status: "coming-soon",
    category: "agent",
    icon: "Building2",
    order: 15,
  },
  {
    id: "fitness-agent",
    name: "Fitness Agent",
    description: "Training plans, habits, and progress tracking.",
    status: "coming-soon",
    category: "agent",
    icon: "Dumbbell",
    order: 16,
  },
  {
    id: "admin-agent",
    name: "Admin Agent",
    description: "Schedules, inbox, and personal admin handled for you.",
    status: "coming-soon",
    category: "agent",
    icon: "CalendarClock",
    order: 17,
  },

  // ── Coming soon (automation) ─────────────────────────────────────────────
  {
    id: "workflow-learning",
    name: "Workflow Learning",
    description:
      "Gummy learns your recurring workflows and offers to run them.",
    status: "coming-soon",
    category: "automation",
    icon: "Sparkles",
    order: 20,
  },
  {
    id: "workflow-automation",
    name: "Workflow Automation",
    description: "Automate multi-step tasks with approval gates.",
    status: "coming-soon",
    category: "automation",
    icon: "Zap",
    order: 21,
  },
  {
    id: "n8n-integration",
    name: "N8N Integration",
    description: "Bring your own workflows and run them safely through Gummy.",
    status: "coming-soon",
    category: "automation",
    icon: "Plug",
    order: 22,
  },

  // ── Future vision ────────────────────────────────────────────────────────
  {
    id: "ai-workforce",
    name: "AI Workforce",
    description: "A coordinated team of agents executing on your behalf.",
    status: "future",
    category: "vision",
    icon: "Users",
    order: 30,
  },
];
