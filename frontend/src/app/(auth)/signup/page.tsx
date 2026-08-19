"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";

import { AuthShell } from "@/components/auth/AuthShell";
import { GoogleButton } from "@/components/auth/GoogleButton";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { buttonVariants } from "@/components/ui/button";
import { useAuth } from "@/components/auth/AuthProvider";
import { MIN_PASSWORD_LENGTH } from "@/lib/auth/passwordPolicy";
import { signUp } from "@/lib/auth/session";
import { analytics, AnalyticsEvent } from "@/lib/analytics";
import { cn } from "@/lib/utils";

function SignUpForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next");
  const { refresh } = useAuth();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < MIN_PASSWORD_LENGTH) {
      toast.error(
        `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`,
      );
      return;
    }
    setSubmitting(true);
    try {
      await signUp(email, password, name);
      await refresh();
      analytics.track(AnalyticsEvent.UserSignedUp, { method: "password" });
      router.replace(next?.startsWith("/") ? next : "/");
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not create your account.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-5">
      <GoogleButton next={next ?? "/"} label="Sign up with Google" />

      <div className="flex items-center gap-3">
        <span className="h-px flex-1 bg-white/10" />
        <span className="text-muted-foreground text-xs">or</span>
        <span className="h-px flex-1 bg-white/10" />
      </div>

      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            autoComplete="name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="What should Gummy call you?"
          />
        </div>
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
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD_LENGTH}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
          />
        </div>
        <button
          type="submit"
          disabled={submitting}
          className={cn(
            buttonVariants({ size: "lg" }),
            "h-11 w-full text-base",
          )}
        >
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>
    </div>
  );
}

export default function SignUpPage() {
  return (
    <AuthShell
      title="Create your account"
      subtitle="Gummy learns you as you talk. Everything stays on your machine."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <Suspense fallback={null}>
        <SignUpForm />
      </Suspense>
    </AuthShell>
  );
}
