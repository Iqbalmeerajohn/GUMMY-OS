/**
 * Server-side instrumentation entrypoint (Node.js + Edge runtimes).
 *
 * `register()` runs once per server instance before requests are served; we
 * load the runtime-appropriate Sentry config there. `onRequestError` forwards
 * every server-side request error (RSC render, route handler, server action)
 * to Sentry — the server counterpart to the client error boundary.
 */

import * as Sentry from "@sentry/nextjs";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

export const onRequestError = Sentry.captureRequestError;
