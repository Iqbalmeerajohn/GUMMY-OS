import type { User } from "@supabase/supabase-js";

import type { UserProfile } from "@/lib/profile/types";

/**
 * The user's first name for greetings.
 *
 * Fallback order: profile.display_name → user_metadata.first_name →
 * full_name/name → "Friend". NEVER the email, email prefix, or UUID — those
 * are identifiers, not names (the "Iqbalmeerajohn1" bug).
 */
export function greetingName(
  profile?: UserProfile | null,
  user?: User | null,
): string {
  const meta = (user?.user_metadata ?? {}) as Record<string, unknown>;
  const str = (v: unknown) => (typeof v === "string" && v.trim() ? v : null);
  const source =
    str(profile?.display_name) ??
    str(meta.first_name) ??
    str(meta.full_name) ??
    str(meta.name);
  if (!source) return "Friend";
  const first = source.trim().split(/[ .]/)[0];
  return first.charAt(0).toUpperCase() + first.slice(1);
}
