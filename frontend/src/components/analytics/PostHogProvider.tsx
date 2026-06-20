"use client";

import type { ReactNode } from "react";
import { PostHogProvider as PHProvider } from "posthog-js/react";
import posthog from "posthog-js";

import { analyticsEnabled } from "@/lib/analytics/config";
import { AnalyticsIdentity } from "@/components/analytics/AnalyticsIdentity";

/**
 * Makes the (already-initialized) PostHog singleton available to the React tree
 * so `posthog-js/react` hooks work, and keeps the analytics identity in sync
 * with the auth session.
 *
 * The client is initialized in `src/instrumentation-client.ts`; this provider
 * only wires it into React. When analytics is disabled (no key) it renders a
 * transparent pass-through.
 */
export function PostHogProvider({ children }: { children: ReactNode }) {
  if (!analyticsEnabled) return <>{children}</>;

  return (
    <PHProvider client={posthog}>
      <AnalyticsIdentity />
      {children}
    </PHProvider>
  );
}
