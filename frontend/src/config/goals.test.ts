/**
 * Tests for the goals presentation config (run with `node --test`).
 *
 * Pure-function coverage: priority/status metadata lookup, fallbacks for
 * unexpected values, and the priority rank ordering the Goals page sorts by.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  GOAL_PRIORITIES,
  GOAL_STATUSES,
  getPriorityMeta,
  getStatusMeta,
} from "./goals.ts";

test("priority metadata resolves by id", () => {
  assert.equal(getPriorityMeta("high").label, "High");
  assert.equal(getPriorityMeta("medium").label, "Medium");
  assert.equal(getPriorityMeta("low").label, "Low");
});

test("priority rank orders high > medium > low", () => {
  assert.equal(getPriorityMeta("high").rank, 3);
  assert.equal(getPriorityMeta("medium").rank, 2);
  assert.equal(getPriorityMeta("low").rank, 1);
  assert.ok(
    getPriorityMeta("high").rank > getPriorityMeta("medium").rank &&
      getPriorityMeta("medium").rank > getPriorityMeta("low").rank,
  );
});

test("status metadata resolves by id", () => {
  assert.equal(getStatusMeta("active").label, "Active");
  assert.equal(getStatusMeta("completed").label, "Completed");
  assert.equal(getStatusMeta("archived").label, "Archived");
});

test("unknown values fall back without throwing", () => {
  // @ts-expect-error — exercising the runtime fallback for an invalid value.
  assert.equal(getPriorityMeta("urgent").id, "medium");
  // @ts-expect-error — exercising the runtime fallback for an invalid value.
  assert.equal(getStatusMeta("paused").id, "active");
});

test("every catalog entry is self-consistent", () => {
  for (const p of GOAL_PRIORITIES) assert.equal(getPriorityMeta(p.id).id, p.id);
  for (const s of GOAL_STATUSES) assert.equal(getStatusMeta(s.id).id, s.id);
});
