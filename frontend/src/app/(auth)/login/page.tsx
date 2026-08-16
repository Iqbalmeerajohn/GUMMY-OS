"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

import { AuthShell } from "@/components/auth/AuthShell";
import { GoogleButton } from "@/components/auth/GoogleButton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { buttonVariants } from "@/components/ui/button";
import { useAuth } from "@/components/auth/AuthProvider";
import { signIn } from "@/lib/auth/session";
import { analytics, AnalyticsEvent } from "@/lib/analytics";
import { cn } from "@/lib/utils";

/** Human-readable text for the error codes the OAuth callback can redirect with. */
const OAUTH_ERRORS: Record<string, string> = {
  access_denied: "You cancelled Google sign-in.",
  oauth_state_invalid: "That sign-in link expired. Please try again.",
  missing_code: "Google did not complete the sign-in. Please try again.",
};

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next");
  const { refresh } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const error = params.get("error");
    if (error) {
      toast.error(OAUTH_ERRORS[error] ?? "Sign-in failed. Please try again.");
    }
  }, [params]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await signIn(email, password);
      await refresh();
      analytics.track(AnalyticsEvent.UserLoggedIn, { method: "password" });
      router.replace(next?.startsWith("/") ? next : "/");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not sign you in.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-5">
      <GoogleButton next={next ?? "/"} label="Continue with Google" />

      <div className="flex items-center gap-3">
        <span className="h-px flex-1 bg-white/10" />
        <span className="text-muted-foreground text-xs">or</span>
        <span className="h-px flex-1 bg-white/10" />
      </div>

      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <Link
              href="/forgot-password"
              className="text-muted-foreground hover:text-foreground text-xs"
            >
              Forgot password?
            </Link>
          </div>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className={cn(buttonVariants({ size: "lg" }), "h-11 w-full text-base")}
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return (
    <AuthShell
      title="Welcome back"
      subtitle="Sign in to your personal AI operating system."
      footer={
        <>
          New to GUMMY?{" "}
          <Link href="/signup" className="text-primary hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </AuthShell>
  );
}
