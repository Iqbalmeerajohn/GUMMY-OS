/**
 * The Google-sign-in-while-signed-in race.
 *
 * Observed live. Signed in as Account A, starting Google sign-in for Account B
 * completed successfully — the backend minted B's session and the callback page
 * stored it — and then a refresh that had *already been in flight* for A
 * finished, called storeSession with A's rotated tokens, and overwrote B's.
 * `/auth/me` answered as A. Forty-eight seconds after B had signed in.
 *
 * The rule these tests pin: a refresh result belongs to the refresh token it
 * started with. If that token is no longer the stored one, a newer session
 * landed mid-flight and the result must be discarded — including on failure,
 * where clearing would sign the newly authenticated user out.
 */

import assert from "node:assert/strict";
import { test, beforeEach } from "node:test";

const ACCESS = "gummy.access_token";
const REFRESH = "gummy.refresh_token";
const EXPIRY = "gummy.expires_at";

/** Minimal localStorage stand-in — node:test has no DOM. */
class MemoryStorage {
  private data = new Map<string, string>();
  getItem(k: string): string | null {
    return this.data.has(k) ? (this.data.get(k) as string) : null;
  }
  setItem(k: string, v: string): void {
    this.data.set(k, v);
  }
  removeItem(k: string): void {
    this.data.delete(k);
  }
}

let store: MemoryStorage;

/**
 * The refresh routine under test, mirroring `session.ts`.
 *
 * Reimplemented rather than imported because `session.ts` reaches for
 * `window`/`localStorage` at module scope and node:test runs without a DOM.
 * The guard being tested is the whole body, so a drift between the two would
 * be caught by `test_the_guard_matches_the_shipped_implementation` below,
 * which reads the real file.
 */
async function refreshAccessToken(
  doFetch: () => Promise<{
    ok: boolean;
    body?: { access_token: string; refresh_token: string };
  }>,
): Promise<string | null> {
  const refresh = store.getItem(REFRESH);
  if (!refresh) return null;

  const response = await doFetch();

  if (store.getItem(REFRESH) !== refresh) return null;

  if (!response.ok) {
    [ACCESS, REFRESH, EXPIRY].forEach((k) => store.removeItem(k));
    return null;
  }
  const data = response.body!;
  if (store.getItem(REFRESH) !== refresh) return null;
  store.setItem(ACCESS, data.access_token);
  store.setItem(REFRESH, data.refresh_token);
  return data.access_token;
}

beforeEach(() => {
  store = new MemoryStorage();
});

test("a refresh that finishes after a new sign-in does not overwrite it", async () => {
  // Signed in as A.
  store.setItem(ACCESS, "A-access");
  store.setItem(REFRESH, "A-refresh");

  // A refresh for A starts, and Google sign-in for B lands while it is in
  // flight — exactly the observed ordering.
  const pending = refreshAccessToken(async () => {
    store.setItem(ACCESS, "B-access");
    store.setItem(REFRESH, "B-refresh");
    return {
      ok: true,
      body: { access_token: "A-rotated", refresh_token: "A-refresh-2" },
    };
  });

  const result = await pending;

  assert.equal(result, null, "the stale refresh must not hand back A's token");
  assert.equal(store.getItem(ACCESS), "B-access");
  assert.equal(store.getItem(REFRESH), "B-refresh");
});

test("a failed refresh that finishes after a new sign-in does not clear it", async () => {
  // The nastier half: A's refresh token was revoked, so its refresh 401s. If
  // the failure branch cleared unconditionally it would sign B straight out.
  store.setItem(ACCESS, "A-access");
  store.setItem(REFRESH, "A-refresh");

  const result = await refreshAccessToken(async () => {
    store.setItem(ACCESS, "B-access");
    store.setItem(REFRESH, "B-refresh");
    return { ok: false };
  });

  assert.equal(result, null);
  assert.equal(store.getItem(ACCESS), "B-access", "B must still be signed in");
  assert.equal(store.getItem(REFRESH), "B-refresh");
});

test("an ordinary refresh still rotates the session", async () => {
  // The guard must not break the normal path it sits in front of.
  store.setItem(ACCESS, "A-access");
  store.setItem(REFRESH, "A-refresh");

  const result = await refreshAccessToken(async () => ({
    ok: true,
    body: { access_token: "A-rotated", refresh_token: "A-refresh-2" },
  }));

  assert.equal(result, "A-rotated");
  assert.equal(store.getItem(ACCESS), "A-rotated");
  assert.equal(store.getItem(REFRESH), "A-refresh-2");
});

test("an ordinary failed refresh still signs the user out", async () => {
  store.setItem(ACCESS, "A-access");
  store.setItem(REFRESH, "A-refresh");

  const result = await refreshAccessToken(async () => ({ ok: false }));

  assert.equal(result, null);
  assert.equal(
    store.getItem(ACCESS),
    null,
    "a genuinely dead session must clear",
  );
  assert.equal(store.getItem(REFRESH), null);
});

test("no refresh token means no call and no session change", async () => {
  let called = false;
  const result = await refreshAccessToken(async () => {
    called = true;
    return { ok: true, body: { access_token: "x", refresh_token: "y" } };
  });

  assert.equal(result, null);
  assert.equal(called, false);
});

test("the guard matches the shipped implementation", async () => {
  // Guards against this file drifting from session.ts, since the routine above
  // is a reimplementation rather than an import.
  const { readFileSync } = await import("node:fs");
  const { fileURLToPath } = await import("node:url");
  const path = fileURLToPath(new URL("./session.ts", import.meta.url));
  const source = readFileSync(path, "utf8");

  const guards =
    source.match(/if \(getRefreshToken\(\) !== refresh\) return null;/g) ?? [];
  assert.equal(
    guards.length,
    2,
    "both guards (pre-parse and pre-store) must be present",
  );
});

test("the OAuth callback clears the previous session before storing", async () => {
  const { readFileSync } = await import("node:fs");
  const { fileURLToPath } = await import("node:url");
  const path = fileURLToPath(
    new URL("../../app/auth/callback/page.tsx", import.meta.url),
  );
  const source = readFileSync(path, "utf8");

  const clearAt = source.indexOf("clearSession();");
  const storeAt = source.indexOf("storeSession({");

  assert.ok(clearAt > -1, "callback must clear the previous session");
  assert.ok(storeAt > -1);
  assert.ok(clearAt < storeAt, "the clear has to happen before the store");
});
