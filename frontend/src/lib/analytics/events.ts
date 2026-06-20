/**
 * Canonical GUMMY analytics event catalog.
 *
 * Every product event GUMMY emits is named here exactly once. Call sites import
 * `AnalyticsEvent` rather than passing raw strings, so the event taxonomy stays
 * consistent (no typos, no drift) and is greppable from one place.
 *
 * Naming: snake_case, `object_action` (past tense for completed actions).
 */
export const AnalyticsEvent = {
  // ── Authentication ──────────────────────────────────────────────────────────
  UserSignedUp: "user_signed_up",
  UserLoggedIn: "user_logged_in",
  UserLoggedOut: "user_logged_out",

  // ── Workspace / conversations ───────────────────────────────────────────────
  WorkspaceOpened: "workspace_opened",
  ConversationCreated: "conversation_created",
  ConversationOpened: "conversation_opened",
  MessageSent: "message_sent",
  AssistantResponseCompleted: "assistant_response_completed",

  // ── Memory system ───────────────────────────────────────────────────────────
  MemoryCreated: "memory_created",
  MemoryUpdated: "memory_updated",
  MemoryRecalled: "memory_recalled",

  // ── Goals ───────────────────────────────────────────────────────────────────
  // Defined for the taxonomy; wired once goal create/complete UI ships (goals
  // are read-only today). Kept here so the event names are agreed in advance.
  GoalCreated: "goal_created",
  GoalCompleted: "goal_completed",

  // ── Dashboard ───────────────────────────────────────────────────────────────
  DashboardViewed: "dashboard_viewed",

  // ── Agents ──────────────────────────────────────────────────────────────────
  AgentSelected: "agent_selected",
  AgentExecuted: "agent_executed",

  // ── Profile ─────────────────────────────────────────────────────────────────
  ProfileUpdated: "profile_updated",
} as const;

/** Union of every valid event name. */
export type AnalyticsEvent =
  (typeof AnalyticsEvent)[keyof typeof AnalyticsEvent];

/** Arbitrary, JSON-serializable event properties. */
export type AnalyticsProperties = Record<string, unknown>;

/** Person properties attached on identify (display name, email, …). */
export type AnalyticsTraits = Record<string, unknown>;
