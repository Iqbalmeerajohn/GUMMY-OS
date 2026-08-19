/**
 * Local session store — tokens issued by GUMMY's own backend.
 *
 * The whole client-side auth layer. Access tokens are short-lived and refreshed
 * transparently, so callers only ever ask for "a valid token" and never deal
 * with expiry themselves.
 *
 * Storage is `localStorage`. That is a deliberate trade for a local-first,
 * single-user desktop app: an httpOnly cookie resists XSS better, but requires
 * the API and the app to share an origin, which breaks the `localhost:3000` →
 * `localhost:8000` split this project runs on. The refresh token is revocable
 * server-side, which bounds the damage.
 */

import { env } from "@/lib/env";

const ACCESS_KEY = "gummy.access_token";
const REFRESH_KEY = "gummy.refresh_token";
const EXPIRY_KEY = "gummy.expires_at";

// Refresh this long before actual expiry, so a request never sets off with a
// token that expires mid-flight.
const REFRESH_SKEW_MS = 60_000;

export interface AuthUser {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  /** Account creation time, ISO-8601. Absent on owner-mode/token-only reads. */
  created_at?: string | null;
}

export interface SessionPayload {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: AuthUser;
}

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

export function storeSession(tokens: {
  access_token: string;
  refresh_token: string;
  expires_in: number;
}): void {
  if (!isBrowser()) return;
  localStorage.setItem(ACCESS_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  localStorage.setItem(
    EXPIRY_KEY,
    String(Date.now() + tokens.expires_in * 1000),
  );
}

export function clearSession(): void {
  if (!isBrowser()) return;
  [ACCESS_KEY, REFRESH_KEY, EXPIRY_KEY].forEach((k) =>
    localStorage.removeItem(k),
  );
}

export function getRefreshToken(): string | null {
  return isBrowser() ? localStorage.getItem(REFRESH_KEY) : null;
}

function isExpired(): boolean {
  if (!isBrowser()) return true;
  const raw = localStorage.getItem(EXPIRY_KEY);
  if (!raw) return true;
  return Date.now() > Number(raw) - REFRESH_SKEW_MS;
}

// A single in-flight refresh shared by all callers. Without this, a page that
// fires several queries at once on load would send several refreshes; since
// refresh tokens rotate, all but one would be rejected and the user would be
// signed out at random.
let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  const response = await fetch(`${env.apiBaseUrl}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!response.ok) {
    clearSession();
    return null;
  }
  const data = (await response.json()) as SessionPayload;
  storeSession(data);
  return data.access_token;
}

/** A valid access token, refreshing first if the current one is near expiry. */
export async function getAccessToken(): Promise<string | null> {
  if (!isBrowser()) return null;
  const token = localStorage.getItem(ACCESS_KEY);
  if (token && !isExpired()) return token;

  if (!refreshInFlight) {
    refreshInFlight = refreshAccessToken().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

/** Fetch the signed-in account, or null when there is no valid session. */
export async function fetchProfile(): Promise<AuthUser | null> {
  const token = await getAccessToken();
  const response = await fetch(`${env.apiBaseUrl}/api/v1/auth/me`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) return null;
  return (await response.json()) as AuthUser;
}

const GENERIC_ERROR = "Something went wrong. Please try again.";

/**
 * Turn an error response body into one sentence a person can act on.
 *
 * Three shapes reach here. The app's own envelope is `{error:{code,message}}`.
 * FastAPI's request-validation failure is `{detail:[{msg,loc},…]}` — an array,
 * which a naive `?? detail` renders as "[object Object]". And a 500 may carry
 * no usable body at all, which is what the fallback is for: a raw traceback is
 * never shown to a user.
 */
function errorMessage(data: unknown, status: number): string {
  const body = (data ?? {}) as {
    error?: { message?: string };
    detail?: unknown;
  };

  if (body.error?.message) return body.error.message;

  if (Array.isArray(body.detail)) {
    const first = body.detail[0] as { msg?: string } | undefined;
    if (first?.msg) {
      // Pydantic prefixes with "Value error, " / "String should have…".
      return first.msg.replace(/^Value error,\s*/, "");
    }
  }
  if (typeof body.detail === "string") return body.detail;

  if (status === 429) return "Too many attempts. Please wait and try again.";
  if (status >= 500) return GENERIC_ERROR;
  return GENERIC_ERROR;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    // The backend is down or unreachable. Distinguish it, because "check your
    // connection" is actionable where the generic message is not.
    throw new Error("Could not reach the server. Is the backend running?");
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(errorMessage(data, response.status));
  }
  return data as T;
}

export async function signIn(
  email: string,
  password: string,
): Promise<SessionPayload> {
  const session = await post<SessionPayload>("/api/v1/auth/login", {
    email,
    password,
  });
  storeSession(session);
  return session;
}

export async function signUp(
  email: string,
  password: string,
  displayName?: string,
): Promise<SessionPayload> {
  const session = await post<SessionPayload>("/api/v1/auth/signup", {
    email,
    password,
    display_name: displayName || null,
  });
  storeSession(session);
  return session;
}

export async function signOut(): Promise<void> {
  const refresh = getRefreshToken();
  clearSession();
  // Best-effort server-side revocation. The local session is already gone, so
  // a network failure here must not leave the user seemingly signed in.
  if (refresh) {
    await fetch(`${env.apiBaseUrl}/api/v1/auth/logout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    }).catch(() => undefined);
  }
}

export interface AuthCapabilities {
  password_enabled: boolean;
  google_enabled: boolean;
  owner_mode: boolean;
  /** True when the backend logs auth email instead of sending it (local dev). */
  email_console_mode: boolean;
}

/** Which sign-in methods this backend supports (drives what the UI offers). */
export async function fetchAuthConfig(): Promise<AuthCapabilities> {
  const response = await fetch(`${env.apiBaseUrl}/api/v1/auth/config`);
  if (!response.ok) {
    return {
      password_enabled: true,
      google_enabled: false,
      owner_mode: false,
      email_console_mode: true,
    };
  }
  return (await response.json()) as AuthCapabilities;
}

/** Start Google sign-in by handing the browser to the backend's OAuth entry. */
export function googleSignInUrl(next = "/"): string {
  return `${env.apiBaseUrl}/api/v1/auth/google/start?next=${encodeURIComponent(next)}`;
}

/**
 * Ask for a password reset link.
 *
 * Resolves for a known and an unknown address alike — the backend answers
 * identically on purpose, so that this endpoint cannot be used to find out
 * which addresses have accounts. The caller must not infer anything from it
 * succeeding.
 */
export async function requestPasswordReset(email: string): Promise<string> {
  const data = await post<{ message: string }>("/api/v1/auth/forgot-password", {
    email,
  });
  return data.message;
}

/** Redeem a reset token and set a new password. Does not sign the user in. */
export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<string> {
  const data = await post<{ message: string }>("/api/v1/auth/reset-password", {
    token,
    new_password: newPassword,
  });
  return data.message;
}
