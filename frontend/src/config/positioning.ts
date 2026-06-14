/**
 * Positioning — "Why GUMMY is Different".
 *
 * GUMMY is a Personal AI Operating System, NOT a chatbot. The comparison below
 * is capability- and vision-focused. The "traditional" column describes typical
 * AI tools neutrally and factually — never derogatory.
 */

import type { ComparisonRow, PositioningStatement } from "./types";

/** What GUMMY is (used in hero / Discover / onboarding). */
export const POSITIONING: PositioningStatement[] = [
  {
    label: "Personal AI Operating System",
    description: "A unified layer for knowledge, goals, memory, and execution.",
  },
  {
    label: "Memory-First Assistant",
    description: "Persistent memory that carries context across every session.",
  },
  {
    label: "Goal Operating System",
    description: "Long-term goals and tasks tracked, not lost between chats.",
  },
  {
    label: "Multi-Agent Platform",
    description: "Specialized agents that collaborate with full traceability.",
  },
  {
    label: "Future Workflow Automation Platform",
    description: "A path to safe, approval-gated automation of real work.",
  },
];

/** Tools GUMMY is commonly compared with (context only — framed positively). */
export const COMPARISON_TOOLS = [
  "ChatGPT",
  "Claude",
  "Gemini",
  "Perplexity",
  "Copilot",
] as const;

/** Capability-focused comparison (neutral "traditional", additive "gummy"). */
export const COMPARISON: ComparisonRow[] = [
  {
    dimension: "Primary mode",
    traditional: "Conversation-focused",
    gummy: "A personal operating system; chat is one tool among many",
  },
  {
    dimension: "Context",
    traditional: "Session-based interaction",
    gummy: "Persistent memory across conversations",
  },
  {
    dimension: "Goals",
    traditional: "Limited long-term goal management",
    gummy: "Built-in goals and task tracking",
  },
  {
    dimension: "Agents",
    traditional: "Single-assistant experience",
    gummy: "Multi-agent collaboration",
  },
  {
    dimension: "Automation",
    traditional: "Limited workflow orchestration",
    gummy: "Future workflow automation and AI workforce",
  },
  {
    dimension: "Experience",
    traditional: "Separate experiences across tools",
    gummy: "A unified personal operating layer",
  },
];
