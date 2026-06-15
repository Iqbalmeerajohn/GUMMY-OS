import { cookies } from "next/headers";
import { createServerClient } from "@supabase/ssr";

import { env } from "@/lib/env";

/**
 * Server-side Supabase client (Server Components, Route Handlers, Server
 * Actions). Bound to the request's cookie jar. The setAll try/catch is the
 * documented pattern: Server Components can't write cookies — proxy.ts refreshes
 * them instead.
 */
export async function getSupabaseServerClient() {
  const cookieStore = await cookies();

  return createServerClient(env.supabaseUrl, env.supabaseAnonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Called from a Server Component — safe to ignore; proxy refreshes.
        }
      },
    },
  });
}
