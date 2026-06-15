"use client";

/**
 * Onboarding completion state.
 *
 * MVP: stored in localStorage. This is the seam that moves to the backend
 * user_profiles API (B1) later — callers only use these helpers, so swapping
 * the storage is contained.
 */

const KEY = "gummy.onboarding.completed";

export function hasCompletedOnboarding(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(KEY) === "true";
}

export function markOnboardingComplete(): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, "true");
}
