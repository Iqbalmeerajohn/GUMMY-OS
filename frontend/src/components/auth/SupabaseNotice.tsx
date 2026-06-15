/** Shown on auth screens when Supabase env vars aren't configured yet. */
export function SupabaseNotice() {
  return (
    <div className="border-border/60 bg-muted/30 text-muted-foreground rounded-xl border p-4 text-center text-sm">
      Authentication isn&apos;t configured yet. Add{" "}
      <code className="text-foreground">NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
      <code className="text-foreground">NEXT_PUBLIC_SUPABASE_ANON_KEY</code> to{" "}
      <code className="text-foreground">.env.local</code> to enable sign-in.
    </div>
  );
}
