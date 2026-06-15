"use client";

import { getProfileSync, saveProfileSync } from "@/lib/profile/storage";

/**
 * Onboarding completion — now backed by the profile store (see
 * lib/profile/storage). Kept as thin sync helpers for routing decisions.
 */

export function hasCompletedOnboarding(): boolean {
  return getProfileSync().onboarding_completed;
}

export function markOnboardingComplete(): void {
  saveProfileSync({ onboarding_completed: true });
}
