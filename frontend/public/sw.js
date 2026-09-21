/**
 * GUMMY service worker — installability and an honest offline page.
 *
 * Deliberately minimal, and the reasoning matters more than the code.
 *
 * **Nothing from /api is ever cached.** Every response here is personal: your
 * memories, your conversations, your goals. A cache of those on disk is a
 * copy of your private data living outside the database, surviving logout,
 * and readable by anything that can reach the browser profile. It is also
 * wrong on its own terms — a stale answer from an assistant is worse than no
 * answer, because you cannot tell which one you are reading.
 *
 * So the cache holds the app shell only: the static assets needed to render
 * a page that says "you are offline". Everything else goes to the network,
 * and when the network is gone, it says so.
 *
 * A service worker also happens to be what makes the app installable on a
 * home screen, which is the actual reason this file exists.
 */

const CACHE = "gummy-shell-v1";
const OFFLINE_URL = "/offline.html";

// The shell only. No routes, because every route is personalised.
const SHELL = [OFFLINE_URL, "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      // Take over without requiring every tab to be closed first.
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Only GET is ever considered; a cached POST would be meaningless and a
  // replayed one would be dangerous.
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Never touch the API or auth. Stale personal data is both a privacy
  // problem and a correctness problem.
  if (url.pathname.startsWith("/api") || url.pathname.startsWith("/auth")) return;

  // Cross-origin requests are left entirely alone.
  if (url.origin !== self.location.origin) return;

  // Navigations: network first, offline page as the fallback. Never serve a
  // cached page — it would show someone else's session state or yesterday's.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match(OFFLINE_URL)),
    );
    return;
  }

  // Static assets: cache first. These are content-hashed by the build, so a
  // cached copy can never be the wrong version of itself.
  if (SHELL.includes(url.pathname) || url.pathname.startsWith("/_next/static")) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ||
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              caches.open(CACHE).then((cache) => cache.put(request, copy));
            }
            return response;
          }),
      ),
    );
  }
});
