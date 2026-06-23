/**
 * Tests for the conversation goal-candidate helpers (run with `node --test`).
 *
 * Pure-function coverage: target-date formatting (valid / null / unparseable)
 * and the candidate → accept/dismiss request-body mapping that the
 * GoalConfirmation flow depends on.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  candidateToCreateBody,
  candidateToDismissBody,
  formatTargetDate,
} from "./goalCandidate.ts";
import type { GoalCandidate } from "../api/resources.ts";

function candidate(overrides: Partial<GoalCandidate> = {}): GoalCandidate {
  return {
    title: "Get an AI Engineer job",
    description: "I want to get an AI Engineer job by July 2nd",
    priority: "high",
    target_date: "2026-07-02T00:00:00Z",
    ...overrides,
  };
}

test("formatTargetDate renders an ISO date in a friendly form", () => {
  const formatted = formatTargetDate("2026-07-02T00:00:00Z");
  assert.ok(formatted);
  // Locale-dependent, but must contain the year and not be "Invalid Date".
  assert.match(formatted as string, /2026/);
  assert.doesNotMatch(formatted as string, /Invalid/);
});

test("formatTargetDate returns null for null/undefined", () => {
  assert.equal(formatTargetDate(null), null);
  assert.equal(formatTargetDate(undefined), null);
});

test("formatTargetDate returns null for an unparseable value", () => {
  assert.equal(formatTargetDate("not-a-date"), null);
});

test("candidateToCreateBody maps fields and ties to the conversation", () => {
  const body = candidateToCreateBody(candidate(), "conv-123");
  assert.deepEqual(body, {
    title: "Get an AI Engineer job",
    description: "I want to get an AI Engineer job by July 2nd",
    priority: "high",
    target_date: "2026-07-02T00:00:00Z",
    conversation_id: "conv-123",
  });
});

test("candidateToCreateBody carries a null conversation id", () => {
  const body = candidateToCreateBody(candidate(), null);
  assert.equal(body.conversation_id, null);
});

test("candidateToDismissBody carries only the identifying fields", () => {
  const body = candidateToDismissBody(
    candidate({ priority: "medium", target_date: null }),
    "conv-9",
  );
  assert.deepEqual(body, {
    title: "Get an AI Engineer job",
    priority: "medium",
    target_date: null,
    conversation_id: "conv-9",
  });
});
