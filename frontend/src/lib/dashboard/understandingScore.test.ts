/**
 * Tests for the User Understanding Score (run with `node --test`).
 *
 * Pure-function coverage: empty state, partial coverage, full coverage, the
 * keyword-detected criteria (education/skills/location), graded memory
 * maturity, and the "teach me more" threshold.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CRITERION_POINTS,
  MATURITY_TARGET,
  MIN_MEMORIES_FOR_PERSONALIZATION,
  computeUnderstandingScore,
  type UnderstandingInput,
} from "./understandingScore.ts";

function input(
  overrides: Partial<UnderstandingInput> = {},
): UnderstandingInput {
  return {
    displayName: null,
    memoryContents: [],
    memoriesByCategory: {},
    memoryCount: 0,
    activeGoalsCount: 0,
    recentActivityCount: 0,
    ...overrides,
  };
}

function criterion(
  result: ReturnType<typeof computeUnderstandingScore>,
  key: string,
) {
  const c = result.criteria.find((x) => x.key === key);
  assert.ok(c, `expected a criterion with key "${key}"`);
  return c;
}

test("empty profile scores zero and flags needsMoreData", () => {
  const result = computeUnderstandingScore(input());
  assert.equal(result.score, 0);
  assert.equal(result.needsMoreData, true);
  assert.ok(result.criteria.every((c) => !c.met && c.earned === 0));
});

test("ten criteria are always returned, each worth 10", () => {
  const result = computeUnderstandingScore(input());
  assert.equal(result.criteria.length, 10);
  assert.ok(result.criteria.every((c) => c.max === CRITERION_POINTS));
});

test("display name alone marks the Name criterion met", () => {
  const result = computeUnderstandingScore(input({ displayName: "Iqbal" }));
  assert.equal(criterion(result, "name").met, true);
  assert.equal(criterion(result, "name").earned, CRITERION_POINTS);
  assert.equal(result.score, CRITERION_POINTS);
});

test("a 'profile' memory category also satisfies Name", () => {
  const result = computeUnderstandingScore(
    input({ memoriesByCategory: { profile: 1 }, memoryCount: 1 }),
  );
  assert.equal(criterion(result, "name").met, true);
});

test("memory categories satisfy career/projects/preferences", () => {
  const result = computeUnderstandingScore(
    input({
      memoriesByCategory: { career: 1, project: 2, preference: 1 },
      memoryCount: 4,
    }),
  );
  assert.equal(criterion(result, "career").met, true);
  assert.equal(criterion(result, "projects").met, true);
  assert.equal(criterion(result, "preferences").met, true);
});

test("education / skills / location are detected from memory content", () => {
  const result = computeUnderstandingScore(
    input({
      memoryContents: [
        "Studied computer science at university",
        "Proficient in Python and a skilled engineer",
        "Lives in Berlin",
      ],
      memoryCount: 3,
    }),
  );
  assert.equal(criterion(result, "education").met, true);
  assert.equal(criterion(result, "skills").met, true);
  assert.equal(criterion(result, "location").met, true);
});

test("goals and recent activity come from backend counts", () => {
  const result = computeUnderstandingScore(
    input({ activeGoalsCount: 2, recentActivityCount: 5 }),
  );
  assert.equal(criterion(result, "goals").met, true);
  assert.equal(criterion(result, "activity").met, true);
});

test("memory maturity is graded 1 point per memory up to the target", () => {
  const half = computeUnderstandingScore(input({ memoryCount: 5 }));
  assert.equal(criterion(half, "maturity").earned, 5);
  assert.equal(criterion(half, "maturity").met, false);

  const full = computeUnderstandingScore(
    input({ memoryCount: MATURITY_TARGET }),
  );
  assert.equal(criterion(full, "maturity").earned, CRITERION_POINTS);
  assert.equal(criterion(full, "maturity").met, true);

  const beyond = computeUnderstandingScore(input({ memoryCount: 50 }));
  assert.equal(criterion(beyond, "maturity").earned, CRITERION_POINTS);
});

test("needsMoreData clears at the memory threshold", () => {
  const below = computeUnderstandingScore(
    input({ memoryCount: MIN_MEMORIES_FOR_PERSONALIZATION - 1 }),
  );
  assert.equal(below.needsMoreData, true);

  const at = computeUnderstandingScore(
    input({ memoryCount: MIN_MEMORIES_FOR_PERSONALIZATION }),
  );
  assert.equal(at.needsMoreData, false);
});

test("a fully-known user scores exactly 100", () => {
  const result = computeUnderstandingScore(
    input({
      displayName: "Iqbal",
      memoriesByCategory: { career: 1, project: 1, preference: 1 },
      memoryContents: [
        "Graduated with a degree in engineering",
        "Expert developer, certified in cloud",
        "Based in London",
      ],
      memoryCount: MATURITY_TARGET,
      activeGoalsCount: 3,
      recentActivityCount: 4,
    }),
  );
  assert.equal(result.score, 100);
  assert.ok(result.criteria.every((c) => c.met));
});

test("score is the sum of earned points and never exceeds 100", () => {
  const result = computeUnderstandingScore(
    input({
      displayName: "A",
      memoriesByCategory: { career: 9, project: 9, preference: 9 },
      memoryContents: [
        "studied at college",
        "skilled engineer",
        "lives in Paris",
      ],
      memoryCount: 99,
      activeGoalsCount: 9,
      recentActivityCount: 9,
    }),
  );
  const summed = result.criteria.reduce((s, c) => s + c.earned, 0);
  assert.equal(result.score, summed);
  assert.ok(result.score <= 100);
});
