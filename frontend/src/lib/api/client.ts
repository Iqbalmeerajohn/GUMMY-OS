/**
 * Minimal typed fetch wrapper over the GUMMY FastAPI backend.
 *
 * M0: transport + error normalization only. The bearer-token provider is wired
 * in M1 (Supabase auth) via `setAuthTokenProvider` so this module stays
 * framework-agnostic and easy to test. All domain calls go through the
 * per-resource modules in `lib/api/resources/*` (added per feature milestone).
 */

import { env } from "@/lib/env";

/** Normalized error shape mirroring the backend's AppError ({code, message}). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type TokenProvider = () => Promise<string | null> | string | null;

let tokenProvider: TokenProvider = () => null;

/** Wired in M1 so requests carry the Supabase access token. */
export function setAuthTokenProvider(provider: TokenProvider): void {
  tokenProvider = provider;
}

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  /** JSON body — serialized automatically. */
  json?: unknown;
  /** Query params appended to the path. */
  query?: Record<string, string | number | boolean | undefined | null>;
}

function buildUrl(path: string, query?: ApiRequestOptions["query"]): string {
  const url = new URL(
    path.startsWith("http") ? path : `${env.apiBaseUrl}${path}`,
  );
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

/** Absolute URL for a backend path (used by streaming, which bypasses apiFetch). */
export function apiUrl(path: string): string {
  return buildUrl(path);
}

/** Auth headers (bearer token, when present) for raw fetch / streaming calls. */
export async function authHeaders(): Promise<Record<string, string>> {
  const token = await tokenProvider();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiFetch<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const { json, query, headers, ...rest } = options;
  const token = await tokenProvider();

  const res = await fetch(buildUrl(path, query), {
    ...rest,
    headers: {
      Accept: "application/json",
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : undefined,
  });

  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;

  if (!res.ok) {
    const code = data?.code ?? data?.error?.code ?? "http_error";
    const message =
      data?.message ?? data?.detail ?? res.statusText ?? "Request failed";
    throw new ApiError(res.status, code, message, data);
  }

  return data as T;
}
