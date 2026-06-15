"use client";

import { defaultProfile, type UserProfile } from "./types";

/**
 * Synchronous localStorage access to the profile. Used by routing decisions that
 * can't await. The async repository wraps these so the storage can later become
 * the backend user_profiles API without touching callers.
 */

const KEY = "gummy.profile";

export function getProfileSync(): UserProfile {
  if (typeof window === "undefined") return defaultProfile();
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return defaultProfile();
    return {
      ...defaultProfile(),
      ...(JSON.parse(raw) as Partial<UserProfile>),
    };
  } catch {
    return defaultProfile();
  }
}

export function saveProfileSync(patch: Partial<UserProfile>): UserProfile {
  const next = { ...getProfileSync(), ...patch };
  if (typeof window !== "undefined") {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  }
  return next;
}
