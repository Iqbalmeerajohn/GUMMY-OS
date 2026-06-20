/**
 * The single GUMMY analytics service.
 *
 * Every component talks to PostHog through this object — never `posthog.capture`
 * directly. That keeps one seam for: disabling analytics (no key), SSR safety,
 * error isolation (a tracking failure must never break a user flow), and a typed
 * event surface.
 *
 * The underlying `posthog` singleton is initialized once in
 * `src/instrumentation-client.ts` (before hydration). This module reuses that
 * same instance.
 */

import posthog from "posthog-js";

import { analyticsEnabled } from "./config";
import type {
  AnalyticsEvent,
  AnalyticsProperties,
  AnalyticsTraits,
} from "./events";

/** Analytics only runs in the browser, and only when a key is configured. */
function active(): boolean {
  return analyticsEnabled && typeof window !== "undefined";
}

/** Never let an analytics failure surface to the user. */
function safe(label: string, fn: () => void): void {
  try {
    fn();
  } catch (err) {
    // Swallow — analytics is best-effort. Surface in dev only.
    if (process.env.NODE_ENV !== "production") {
      console.warn(`[analytics] ${label} failed`, err);
    }
  }
}

export const analytics = {
  /** Whether events will actually be sent (key present, in browser). */
  get enabled(): boolean {
    return active();
  },

  /** Record a product event with optional properties. */
  track(event: AnalyticsEvent, properties?: AnalyticsProperties): void {
    if (!active()) return;
    safe(`track:${event}`, () => posthog.capture(event, properties));
  },

  /**
   * Associate the current session with a known user and set person properties.
   * Idempotent — safe to call on every auth state change.
   */
  identify(userId: string, traits?: AnalyticsTraits): void {
    if (!active() || !userId) return;
    safe("identify", () => posthog.identify(userId, traits));
  },

  /** Clear identity on logout so the next user starts a fresh anonymous session. */
  reset(): void {
    if (!active()) return;
    safe("reset", () => posthog.reset());
  },

  /**
   * Report a handled error to PostHog Error Tracking. Unhandled errors and
   * promise rejections are captured automatically by the SDK; use this for
   * caught failures (e.g. API errors) you still want visibility into.
   */
  captureException(error: unknown, context?: AnalyticsProperties): void {
    if (!active()) return;
    const err = error instanceof Error ? error : new Error(String(error));
    safe("captureException", () => posthog.captureException(err, context));
  },
} as const;

export type Analytics = typeof analytics;
