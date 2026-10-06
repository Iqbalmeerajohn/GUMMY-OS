"use client";

import { useEffect } from "react";

/**
 * Registers the service worker that makes GUMMY installable.
 *
 * Client-only and deliberately silent. Registration failing is not a
 * user-facing problem — the app works identically without it, minus
 * installability and the offline page — so a failure is logged for a
 * developer and never surfaced as an error the user has to think about.
 *
 * Skipped in development: an active service worker intercepting fetches
 * fights with hot reload and produces stale-asset bugs that look like
 * application bugs.
 */
export function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;

    // Registering after load keeps the worker off the critical path for the
    // first paint, which is the one the user judges the app on.
    const register = () => {
      navigator.serviceWorker.register("/sw.js").catch((error) => {
        console.warn("service worker registration failed", error);
      });
    };

    if (document.readyState === "complete") {
      register();
      return;
    }
    window.addEventListener("load", register);
    return () => window.removeEventListener("load", register);
  }, []);

  return null;
}
