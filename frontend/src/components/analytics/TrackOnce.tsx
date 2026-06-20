"use client";

import { useEffect, useRef } from "react";

import { analytics } from "@/lib/analytics";
import type { AnalyticsEvent, AnalyticsProperties } from "@/lib/analytics";

/**
 * Fires a single analytics event once when mounted. Renders nothing.
 *
 * Lets a Server Component page (which can't call analytics directly) emit a
 * view event by dropping `<TrackOnce event={...} />` into its tree.
 */
export function TrackOnce({
  event,
  properties,
}: {
  event: AnalyticsEvent;
  properties?: AnalyticsProperties;
}) {
  const fired = useRef(false);
  useEffect(() => {
    if (fired.current) return;
    fired.current = true;
    analytics.track(event, properties);
    // Event identity is stable for a given mount; intentionally fire-once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return null;
}
