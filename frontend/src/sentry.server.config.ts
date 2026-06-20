/**
 * Sentry initialization for the Node.js server runtime (RSC, route handlers,
 * server actions). Loaded by `instrumentation.ts` via `register()`.
 *
 * No-op when the DSN is unset.
 */

import * as Sentry from "@sentry/nextjs";

import {
  SENTRY_DSN,
  SENTRY_ENVIRONMENT,
  SENTRY_TRACES_SAMPLE_RATE,
  sentryEnabled,
} from "@/lib/monitoring/config";

if (sentryEnabled) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: SENTRY_ENVIRONMENT,
    tracesSampleRate: SENTRY_TRACES_SAMPLE_RATE,
    // Don't attach IP/cookies/headers that could carry PII. GUMMY handles
    // private user data, so default to the privacy-safe setting.
    sendDefaultPii: false,
  });
}
