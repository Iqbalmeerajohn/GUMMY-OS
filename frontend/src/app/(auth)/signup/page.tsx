"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { AuthShell } from "@/components/auth/AuthShell";
import { SupabaseNotice } from "@/components/auth/SupabaseNotice";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { buttonVariants } from "@/components/ui/button";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import { resolvePostAuthDestination } from "@/lib/auth/post-auth";
import { env } from "@/lib/env";
import { cn } from "@/lib/utils";

function SignupForm() {
  const router = useRouter();
  const supabase = getSupabaseBrowserClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  if (!supabase) return <SupabaseNotice />;

  if (sent) {
    return (
      <p className="text-muted-foreground text-center text-sm text-balance">
        We sent a confirmation link to{" "}
        <span className="text-foreground">{email}</span>. Click it to verify and
        you&apos;ll come straight back into GUMMY.
      </p>
    );
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    const { data, error } = await supabase!.auth.signUp({
      email,
      password,
      options: {
        emailRedirectTo: `${env.appUrl}/auth/callback?next=/onboarding`,
      },
    });
    setSubmitting(false);
    if (error) {
      toast.error(error.message);
      return;
    }
    if (data.session) {
      // Auto-confirmed → straight into the onboarding journey.
      router.replace(resolvePostAuthDestination("/onboarding"));
    } else {
      setSent(true);
    }
  }

  return (
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
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="At least 8 characters"
        />
      </div>
      <button
        type="submit"
        disabled={submitting}
        className={cn(buttonVariants({ size: "lg" }), "h-11 w-full text-base")}
      >
        {submitting ? "Creating account…" : "Create account"}
      </button>
    </form>
  );
}

export default function SignupPage() {
  return (
    <AuthShell
      title="Create your GUMMY"
      subtitle="Start building memory, goals, and a team of agents."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="text-primary hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <SignupForm />
    </AuthShell>
  );
}
