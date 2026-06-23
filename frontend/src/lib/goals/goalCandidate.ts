/**
 * Pure helpers for conversation-detected goal candidates (M5.5).
 *
 * Kept free of React / browser APIs so the candidate→request mapping and the
 * target-date formatting can be unit-tested in isolation (see
 * `goalCandidate.test.ts`). The `GoalConfirmation` component composes these.
 */

import type {
  GoalCandidate,
  GoalCandidateDismissBody,
  GoalFromConversationBody,
} from "@/lib/api/resources";

/**
 * Human-friendly target date ("Jul 2, 2026") for the confirmation card, or null
 * when the candidate has no date. Parses the backend's ISO string; an
 * unparseable value degrades to null rather than rendering "Invalid Date".
 */
export function formatTargetDate(
  iso: string | null | undefined,
): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/**
 * Map a confirmed candidate to the accept-endpoint request body, tying it back
 * to the conversation it was detected in (for `goal_source = conversation`).
 */
export function candidateToCreateBody(
  candidate: GoalCandidate,
  conversationId: string | null,
): GoalFromConversationBody {
  return {
    title: candidate.title,
    description: candidate.description,
    priority: candidate.priority,
    target_date: candidate.target_date,
    conversation_id: conversationId,
  };
}

/** Map a dismissed candidate to the dismiss-endpoint request body. */
export function candidateToDismissBody(
  candidate: GoalCandidate,
  conversationId: string | null,
): GoalCandidateDismissBody {
  return {
    title: candidate.title,
    priority: candidate.priority,
    target_date: candidate.target_date,
    conversation_id: conversationId,
  };
}
