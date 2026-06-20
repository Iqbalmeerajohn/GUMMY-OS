"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { syncDisplayNameToAuth } from "./identitySync";
import { getProfileRepository } from "./repository";
import type { UserProfile } from "./types";

const repo = getProfileRepository();
const KEY = ["profile"];

/** Reactive read of the current user profile. */
export function useProfile() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => repo.get(),
    staleTime: Infinity,
  });
}

/** Update the profile and refresh the cache. */
export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (patch: Partial<UserProfile>) => {
      const next = await repo.update(patch);
      // Mirror the name into the Supabase JWT so the backend (and every agent)
      // knows who the user is. Best-effort; never blocks the profile save.
      if (typeof patch.display_name === "string") {
        await syncDisplayNameToAuth(patch.display_name);
      }
      return next;
    },
    onSuccess: (next) => qc.setQueryData(KEY, next),
  });
}
