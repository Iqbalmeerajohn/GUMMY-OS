"use client";

import { useEffect, useRef } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { syncDisplayNameToAuth } from "@/lib/profile/identitySync";
import { getProfileSync } from "@/lib/profile/storage";

/**
 * One-shot identity reconciliation. Renders nothing.
 *
 * Existing users set their name before name-sync existed, so it lives only in
 * localStorage and the JWT carries none — the backend can't know who they are.
 * On first authenticated mount, if a local display name exists but the token's
 * `user_metadata` lacks one, push it up so GUMMY learns the user's name without
 * them having to re-save their profile.
 */
export function IdentitySync() {
  const { user } = useAuth();
  const synced = useRef(false);

  useEffect(() => {
    if (!user || synced.current) return;
    const meta = (user.user_metadata ?? {}) as Record<string, unknown>;
    const hasName =
      typeof meta.full_name === "string" || typeof meta.name === "string";
    const local = getProfileSync().display_name?.trim();
    if (!hasName && local) {
      synced.current = true;
      void syncDisplayNameToAuth(local);
    }
  }, [user]);

  return null;
}
