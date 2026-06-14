/**
 * Typed, centralized access to public environment variables.
 *
 * Only NEXT_PUBLIC_* values are safe in the browser. Secrets (service-role keys,
 * the JWT secret, API keys) live on the backend and must never be referenced here.
 */

export const env = {
  /** FastAPI base URL (e.g. http://localhost:8000). */
  apiBaseUrl:
    process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
    "http://localhost:8000",
  /** Public app URL (e.g. http://localhost:3000). */
  appUrl: process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000",
  /** Supabase project URL (browser-safe). Used from M1 (auth). */
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  /** Supabase anon key (browser-safe; RLS enforces access). Used from M1. */
  supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "",
} as const;
