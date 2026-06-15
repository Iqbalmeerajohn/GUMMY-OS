"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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
    mutationFn: (patch: Partial<UserProfile>) => repo.update(patch),
    onSuccess: (next) => qc.setQueryData(KEY, next),
  });
}
