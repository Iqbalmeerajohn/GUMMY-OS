/**
 * The single GUMMY analytics seam — local-only.
 *
 * GUMMY runs on the user's own machine, so product telemetry never leaves it.
 * This module keeps the typed call sites (`analytics.track(...)`) that the app
 * is already written against, but the sink is the dev console instead of a
 * hosted collector. Keeping the seam (rather than deleting every call) means
 * an opt-in local sink can be added later in one file.
 */

import type {
  AnalyticsEvent,
  AnalyticsProperties,
  AnalyticsTraits,
} from "./events";

/** Events are only "recorded" in development, and only in the browser. */
const active =
  process.env.NODE_ENV !== "production" && typeof window !== "undefined";

function log(kind: string, ...args: unknown[]): void {
  if (active) console.debug(`[analytics] ${kind}`, ...args);
}

export const analytics = {
  /** Always false: nothing is transmitted off-device. */
  get enabled(): boolean {
    return false;
  },

  track(event: AnalyticsEvent, properties?: AnalyticsProperties): void {
    log(event, properties);
  },

  identify(userId: string, traits?: AnalyticsTraits): void {
    log("identify", userId, traits);
  },

  reset(): void {
    log("reset");
  },

  /**
   * A handled failure worth seeing. Logged loudly in development; in production
   * it is deliberately silent rather than shipped to a third party.
   */
  captureException(error: unknown, context?: AnalyticsProperties): void {
    if (!active) return;
    console.warn("[analytics] exception", error, context);
  },
} as const;

export type Analytics = typeof analytics;
