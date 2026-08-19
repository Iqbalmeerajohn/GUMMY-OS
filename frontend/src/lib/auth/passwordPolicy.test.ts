import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MAX_PASSWORD_LENGTH,
  MIN_PASSWORD_LENGTH,
  validateNewPassword,
} from "./passwordPolicy.ts";

test("accepts a password that meets the policy and matches its confirmation", () => {
  assert.equal(
    validateNewPassword("Str0ng-Passw0rd!", "Str0ng-Passw0rd!"),
    null,
  );
});

test("rejects a password shorter than the minimum", () => {
  const message = validateNewPassword("short", "short");
  assert.match(message ?? "", /at least 8 characters/);
});

test("rejects a password longer than the maximum", () => {
  const long = "a".repeat(MAX_PASSWORD_LENGTH + 1);
  const message = validateNewPassword(long, long);
  assert.match(message ?? "", /at most 128 characters/);
});

test("rejects a confirmation that does not match", () => {
  const message = validateNewPassword("Str0ng-Passw0rd!", "Str0ng-Passw0rd?");
  assert.equal(message, "Those passwords don't match.");
});

test("reports the length problem before the mismatch", () => {
  // Both are wrong here. Telling someone their four-character password doesn't
  // match is true and useless; the length is the thing they have to fix.
  const message = validateNewPassword("abc", "xyz");
  assert.match(message ?? "", /at least 8 characters/);
});

test("a password of exactly the minimum length is accepted", () => {
  const exact = "a".repeat(MIN_PASSWORD_LENGTH);
  assert.equal(validateNewPassword(exact, exact), null);
});

test("an empty confirmation is a mismatch, not a crash", () => {
  const message = validateNewPassword("Str0ng-Passw0rd!", "");
  assert.equal(message, "Those passwords don't match.");
});
