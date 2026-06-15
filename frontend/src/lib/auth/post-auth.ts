"use client";

import { getProfileSync } from "@/lib/profile/storage";

/**
 * Where an authenticated user should land, based on first-run progress:
 *   no onboarding  → /onboarding (the guided tour)
 *   no display_name → /welcome    (identity + personality setup)
 *   otherwise       → the requested route, or /dashboard
 */
export function resolvePostAuthDestination(next?: string | null): string {
  const profile = getProfileSync();
  if (!profile.onboarding_completed) return "/onboarding";
  if (!profile.display_name) return "/welcome";
  return next && next.startsWith("/") ? next : "/dashboard";
}
