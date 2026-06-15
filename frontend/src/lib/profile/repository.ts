"use client";

import { getProfileSync, saveProfileSync } from "./storage";
import type { UserProfile } from "./types";

/**
 * Profile persistence abstraction.
 *
 * Swap the active implementation to move from localStorage to the backend
 * `user_profiles` table (B1) — callers (the useProfile hook) are unaffected.
 */
export interface ProfileRepository {
  get(): Promise<UserProfile>;
  update(patch: Partial<UserProfile>): Promise<UserProfile>;
}

const localStorageRepository: ProfileRepository = {
  async get() {
    return getProfileSync();
  },
  async update(patch) {
    return saveProfileSync(patch);
  },
};

// Future: an apiProfileRepository backed by GET/PATCH /api/v1/me/profile.
export function getProfileRepository(): ProfileRepository {
  return localStorageRepository;
}
