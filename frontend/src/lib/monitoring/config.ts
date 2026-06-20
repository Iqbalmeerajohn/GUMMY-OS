/**
 * Sentry configuration, derived from environment variables.
 *
 * Monitoring is a no-op whenever the DSN is unset, so dev/preview builds never
 * send events unless explicitly configured. The DSN is browser-safe (it only
 * permits writing events, not reading them).
 *
 * Resolution is written so the SAME module works on the client (where only
 * `NEXT_PUBLIC_*` is inlined) and on the server/edge (where the unprefixed
 * vars are also available).
 */

/** Sentry DSN. Empty string ⇒ monitoring disabled. */
export const SENTRY_DSN =
  process.env.NEXT_PUBLIC_SENTRY_DSN ?? process.env.SENTRY_DSN ?? "";

/** Deploy environment tag (production / preview / development). */
export const SENTRY_ENVIRONMENT =
  process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ??
  process.env.SENTRY_ENVIRONMENT ??
  process.env.NODE_ENV ??
  "development";

/** Performance trace sample rate (0–1). Default 10%. */
export const SENTRY_TRACES_SAMPLE_RATE = Number(
  process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ??
    process.env.SENTRY_TRACES_SAMPLE_RATE ??
    "0.1",
);

/**
 * True only when a DSN is present. Every Sentry entry point checks this so the
 * SDK never initializes (no network, no overhead) without configuration.
 */
export const sentryEnabled = SENTRY_DSN.length > 0;
