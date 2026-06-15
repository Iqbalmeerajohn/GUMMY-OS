/**
 * Conversation agent contexts — the backend `agent_context` enum values the
 * workspace agent selector binds to (general/career/learning/research/builder).
 */
export const AGENT_CONTEXTS = [
  { value: "general", label: "General" },
  { value: "career", label: "Career" },
  { value: "learning", label: "Learning" },
  { value: "research", label: "Research" },
  { value: "builder", label: "Builder" },
] as const;
