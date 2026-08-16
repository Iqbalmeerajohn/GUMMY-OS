"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { setAuthTokenProvider } from "@/lib/api/client";
import {
  clearSession,
  fetchProfile,
  getAccessToken,
  signOut as revokeSession,
  type AuthUser,
} from "@/lib/auth/session";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  signOut: () => Promise<void>;
  /** Re-read the session from the backend (after login or OAuth callback). */
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const SESSION_KEY = ["auth", "session"] as const;

// Feed the API client a token getter once, at module scope. It is stateless and
// reads storage on each call, so it never goes stale — doing this in an effect
// would leave the first render's requests unauthenticated.
setAuthTokenProvider(() => getAccessToken());

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  // The session is server state, so it is fetched like server state. A 200 with
  // owner mode on means the backend signed us in without a token, which is the
  // intended local single-user experience.
  const { data, isPending, refetch } = useQuery({
    queryKey: SESSION_KEY,
    queryFn: () => fetchProfile().catch(() => null),
    staleTime: Infinity,
    retry: false,
  });

  const refresh = useCallback(async () => {
    await refetch();
  }, [refetch]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user: data ?? null,
      loading: isPending,
      refresh,
      signOut: async () => {
        await revokeSession();
        clearSession();
        // Anything cached under the old identity is no longer ours to show —
        // cleared first, so the session we write next survives.
        queryClient.clear();
        queryClient.setQueryData(SESSION_KEY, null);
      },
    }),
    [data, isPending, refresh, queryClient],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
