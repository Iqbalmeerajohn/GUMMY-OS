"use client";

import { useEffect, useRef } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { useProfile } from "@/lib/profile/useProfile";
import { analytics } from "@/lib/analytics";

/**
 * Keeps the PostHog identity in lockstep with the auth session. Renders nothing.
 *
 *   authenticated → identify(user_id, { display_name, email })
 *   logged out    → reset() so the next user starts a clean anonymous session
 *
 * This is the single place identify/reset happen, so no component has to
 * remember to do it. Re-identifying when the display name loads (or changes)
 * keeps the person profile's `display_name` current.
 */
export function AnalyticsIdentity() {
  const { user } = useAuth();
  const { data: profile } = useProfile();
  // The id we last identified, so we only reset on a real logout transition.
  const identifiedId = useRef<string | null>(null);

  const displayName = profile?.display_name?.trim() || undefined;

  useEffect(() => {
    if (user) {
      analytics.identify(user.id, {
        user_id: user.id,
        display_name: displayName,
        email: user.email ?? undefined,
      });
      identifiedId.current = user.id;
    } else if (identifiedId.current) {
      // Transitioned from authenticated → anonymous: clear the identity.
      analytics.reset();
      identifiedId.current = null;
    }
  }, [user, displayName]);

  return null;
}
