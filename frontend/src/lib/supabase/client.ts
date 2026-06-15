"use client";

import { createBrowserClient } from "@supabase/ssr";

import { env } from "@/lib/env";

/** True only when the Supabase env vars are present. */
export function isSupabaseConfigured(): boolean {
  return Boolean(env.supabaseUrl && env.supabaseAnonKey);
}

type BrowserClient = ReturnType<typeof createBrowserClient>;

let browserClient: BrowserClient | null = null;

/**
 * Browser Supabase client (singleton), or null if env is not configured yet.
 * Callers (AuthProvider, auth pages) handle the null case gracefully so the app
 * runs before Supabase is wired up.
 */
export function getSupabaseBrowserClient(): BrowserClient | null {
  if (!isSupabaseConfigured()) return null;
  if (!browserClient) {
    browserClient = createBrowserClient(env.supabaseUrl, env.supabaseAnonKey);
  }
  return browserClient;
}
