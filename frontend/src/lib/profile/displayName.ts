import type { AuthUser } from "@/lib/auth/session";
import type { UserProfile } from "@/lib/profile/types";

/**
 * The user's first name for greetings.
 *
 * Fallback order: the locally-edited profile name → the name on the account →
 * "Friend". NEVER the email, email prefix, or UUID — those are identifiers, not
 * names (the "Iqbalmeerajohn1" bug).
 */
export function greetingName(
  profile?: UserProfile | null,
  user?: AuthUser | null,
): string {
  const str = (v: unknown) => (typeof v === "string" && v.trim() ? v : null);
  const source = str(profile?.display_name) ?? str(user?.display_name);
  if (!source) return "Friend";
  const first = source.trim().split(/[ .]/)[0];
  return first.charAt(0).toUpperCase() + first.slice(1);
}
