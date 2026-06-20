/**
 * Client-side PostHog initialization.
 *
 * Next.js runs this file after the document loads but BEFORE React hydration, so
 * analytics, session replay, and error tracking are live for the earliest part
 * of the app lifecycle (and can capture errors thrown during hydration).
 *
 * Initialization happens exactly once here; the rest of the app talks to the
 * same singleton through `@/lib/analytics`.
 */

import posthog from "posthog-js";

import {
  POSTHOG_HOST,
  POSTHOG_KEY,
  POSTHOG_UI_HOST,
  analyticsEnabled,
} from "@/lib/analytics/config";

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
