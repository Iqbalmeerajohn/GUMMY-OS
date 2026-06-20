/**
 * Sentry initialization for the Edge runtime (proxy/middleware and any
 * edge-rendered routes). Loaded by `instrumentation.ts` via `register()`.
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
    sendDefaultPii: false,
  });
}
