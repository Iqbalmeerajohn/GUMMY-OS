/**
 * The client-side half of the password policy.
 *
 * One definition, shared by the sign-up and reset-password forms. Each screen
 * used to carry its own `MIN_PASSWORD_LENGTH`, which is exactly how a reset
 * flow drifts into accepting something sign-up would have refused.
 *
 * This mirrors the backend's `Password` bound in `app/schemas/auth.py` — it
 * does not replace it. The server is the authority; this exists so the user is
 * told before the round-trip instead of by a 422.
 */

/** Must match `MIN_PASSWORD_LENGTH` in the backend's auth schemas. */
export const MIN_PASSWORD_LENGTH = 8;

/** Must match `MAX_PASSWORD_LENGTH` in the backend's auth schemas. */
export const MAX_PASSWORD_LENGTH = 128;

/**
 * Check a new password and its confirmation.
 *
 * Returns the message to show, or `null` when the input is acceptable. Order
 * matters: complaining that the passwords don't match is unhelpful when the
 * real problem is that the first one is four characters long.
 */
export function validateNewPassword(
  password: string,
  confirmation: string,
): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (password.length > MAX_PASSWORD_LENGTH) {
    return `Password must be at most ${MAX_PASSWORD_LENGTH} characters.`;
  }
  if (password !== confirmation) {
    return "Those passwords don't match.";
  }
  return null;
}
