/**
 * Client-side instrumentation: PostHog (analytics + replay) and Sentry
 * (error monitoring + performance traces).
 *
 * Next.js runs this file after the document loads but BEFORE React hydration, so
 * both are live for the earliest part of the app lifecycle (and can capture
 * errors thrown during hydration). Each init is independently guarded by its own
 * key/DSN, so either can be configured without the other.
 */

import posthog from "posthog-js";
import * as Sentry from "@sentry/nextjs";

import {
  POSTHOG_HOST,
  POSTHOG_KEY,
  POSTHOG_UI_HOST,
  analyticsEnabled,
} from "@/lib/analytics/config";
import {
  SENTRY_DSN,
  SENTRY_ENVIRONMENT,
  SENTRY_TRACES_SAMPLE_RATE,
  sentryEnabled,
} from "@/lib/monitoring/config";

if (analyticsEnabled) {
  posthog.init(POSTHOG_KEY, {
    api_host: POSTHOG_HOST,
    ui_host: POSTHOG_UI_HOST,

    // Modern PostHog defaults: automatic SPA pageview + pageleave capture (via
    // history API), sensible autocapture, etc. Avoids hand-rolled route tracking.
    defaults: "2025-05-24",

    // Only build person profiles for users we explicitly identify (auth'd users),
    // not every anonymous visitor — cleaner data, lower cost.
    person_profiles: "identified_only",

    // ── Error tracking ───────────────────────────────────────────────────────
    // Autocapture unhandled exceptions and unhandled promise rejections.
    capture_exceptions: true,

    // ── Session replay (privacy-safe defaults) ───────────────────────────────
    // GUMMY handles private chat, memories, and profile data, so mask aggressively:
    // every input value is masked, and any element marked data-ph-mask (or the
    // common "ph-mask" class) has its text masked too. Replay must still be turned
    // on in the PostHog project settings for recordings to be produced.
    session_recording: {
      maskAllInputs: true,
      maskInputOptions: { password: true, email: true },
      maskTextSelector: "[data-ph-mask], .ph-mask",
    },
  });
}

// ── Sentry: browser error monitoring + performance traces ────────────────────
// Captures React render errors (via the global-error boundary), unhandled
// exceptions, unhandled promise rejections, and browser crashes. Session replay
// is intentionally left to PostHog to avoid recording the page twice.
if (sentryEnabled) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: SENTRY_ENVIRONMENT,
    tracesSampleRate: SENTRY_TRACES_SAMPLE_RATE,
    sendDefaultPii: false,
  });
}

// App Router navigation instrumentation — lets Sentry tie performance traces to
// client-side route transitions. Exported no-op-safe even when Sentry is off.
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
