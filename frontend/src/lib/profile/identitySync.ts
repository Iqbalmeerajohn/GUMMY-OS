"use client";

import { getSupabaseBrowserClient } from "@/lib/supabase/client";

/**
 * Push the user's display name into Supabase auth `user_metadata` so it travels
 * inside the signed JWT.
 *
 * This is what lets GUMMY know who the user is: the backend reads the name from
 * the verified access token (`user_metadata.full_name` / `name`) and injects it
 * as the identity block into every agent prompt. Without this sync the name
 * lives only in localStorage and never reaches the backend — so "What's my
 * name?" comes back as "I don't know."
 *
 * Best-effort: a failure (offline, Supabase not configured) must never block the
 * local profile save. Returns true only when the metadata was actually updated.
 */
export async function syncDisplayNameToAuth(
  displayName: string,
): Promise<boolean> {
  const name = displayName.trim();
  if (!name) return false;

  const supabase = getSupabaseBrowserClient();
  if (!supabase) return false;

  try {
    const { data } = await supabase.auth.getUser();
    const meta = (data.user?.user_metadata ?? {}) as Record<string, unknown>;
    // Skip the network round-trip (and token refresh) when already current.
    if (meta.full_name === name && meta.name === name) return false;

    const { error } = await supabase.auth.updateUser({
      data: { full_name: name, name },
    });
    return !error;
  } catch {
    return false;
  }
}
