/**
 * Typed, centralized access to public environment variables.
 *
 * Only NEXT_PUBLIC_* values are safe in the browser. Secrets (the JWT secret,
 * API keys, OAuth client secrets) live on the backend and are never referenced
 * here.
 */

export const env = {
  /** FastAPI base URL (e.g. http://localhost:8000). */
  apiBaseUrl:
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
    "http://localhost:8000",
  /** Public app URL (e.g. http://localhost:3000). */
  appUrl: process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000",
} as const;
