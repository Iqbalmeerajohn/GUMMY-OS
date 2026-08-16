"use client";

import { Suspense, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { useAuth } from "@/components/auth/AuthProvider";
import { storeSession } from "@/lib/auth/session";

/**
 * OAuth landing page — receives the session the backend minted after Google.
 *
 * This must be a client component. The backend returns the tokens in the URL
 * *fragment* (`#access_token=…`), which browsers deliberately never transmit to
 * a server — that is what keeps credentials out of access logs and `Referer`
 * headers. A server route handler would therefore see nothing at all.
 *
 * The fragment is cleared from history immediately after being read, so the
 * tokens do not linger in the address bar or in the back/forward stack.
 */
function CallbackHandler() {
  const router = useRouter();
  const params = useSearchParams();
  const { refresh } = useAuth();

  useEffect(() => {
    const next = params.get("next") || "/";
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const accessToken = fragment.get("access_token");
    const refreshToken = fragment.get("refresh_token");

    if (!accessToken || !refreshToken) {
      router.replace("/login?error=missing_code");
      return;
    }

    storeSession({
      access_token: accessToken,
      refresh_token: refreshToken,
      expires_in: Number(fragment.get("expires_in") ?? 3600),
    });

    // Drop the credentials out of the URL before navigating on.
    window.history.replaceState(null, "", window.location.pathname);

    void refresh().then(() => router.replace(next));
  }, [params, router, refresh]);

  return (
    <main className="flex min-h-[100svh] items-center justify-center">
      <p className="text-muted-foreground text-sm">Signing you in…</p>
    </main>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={null}>
      <CallbackHandler />
    </Suspense>
  );
}
