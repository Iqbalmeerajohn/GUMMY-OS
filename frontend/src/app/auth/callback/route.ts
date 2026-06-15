import { NextResponse, type NextRequest } from "next/server";

import { env } from "@/lib/env";
import { getSupabaseServerClient } from "@/lib/supabase/server";

/**
 * Supabase auth callback — exchanges the PKCE `code` for a session (email
 * verification, password recovery, future OAuth) and redirects to `next`.
 * On failure, sends the user to /login with a flag so the UI can explain.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/dashboard";

  if (code && env.supabaseUrl && env.supabaseAnonKey) {
    const supabase = await getSupabaseServerClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return NextResponse.redirect(`${origin}${next}`);
    }
  }

  return NextResponse.redirect(`${origin}/login?verify=failed`);
}
