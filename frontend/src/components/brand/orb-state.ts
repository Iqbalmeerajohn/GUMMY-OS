/**
 * The Living Orb's presence states (drives motion, not color).
 *
 * `idle`/`thinking`/`update` are live today. `listening`, `agent-working`,
 * `approval-needed`, and `workflow-learning` are extension points reserved for
 * future milestones — defined here and given motion targets, not yet triggered
 * by real events.
 */
export type OrbState =
  | "idle"
  | "thinking"
  | "listening"
  | "update"
  | "agent-working"
  | "approval-needed"
  | "workflow-learning";
