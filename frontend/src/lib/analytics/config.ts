/**
 * PostHog configuration, derived from public environment variables.
 *
 * Only NEXT_PUBLIC_* values are exposed here — the project API key is a *write-
 * only* ingestion key (safe in the browser), not a secret. Analytics is a no-op
 * whenever `NEXT_PUBLIC_POSTHOG_KEY` is unset, so local/dev and preview builds
 * never emit events unless explicitly configured.
 */

/** Write-only PostHog project key. Empty string ⇒ analytics disabled. */
export const POSTHOG_KEY = process.env.NEXT_PUBLIC_POSTHOG_KEY ?? "";

/** Ingestion host (events + session replay). US cloud by default; EU users set
 *  https://eu.i.posthog.com. */
export const POSTHOG_HOST =
  process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://us.i.posthog.com";

/** Dashboard host used for "view in PostHog" deep links (not ingestion). */
export const POSTHOG_UI_HOST =
  process.env.NEXT_PUBLIC_POSTHOG_UI_HOST ?? "https://us.posthog.com";

/**
 * True only when a key is present. Every analytics entry point checks this so
 * the rest of the app can call `analytics.*` unconditionally.
 */
export const analyticsEnabled = POSTHOG_KEY.length > 0;
