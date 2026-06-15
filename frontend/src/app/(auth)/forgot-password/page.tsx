"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import { AuthShell } from "@/components/auth/AuthShell";
import { SupabaseNotice } from "@/components/auth/SupabaseNotice";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { buttonVariants } from "@/components/ui/button";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import { env } from "@/lib/env";
import { cn } from "@/lib/utils";

function ForgotForm() {
  const supabase = getSupabaseBrowserClient();
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  if (!supabase) return <SupabaseNotice />;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    const { error } = await supabase!.auth.resetPasswordForEmail(email, {
      redirectTo: `${env.appUrl}/auth/callback?next=/reset-password`,
    });
    setSubmitting(false);
    if (error) {
      toast.error(error.message);
      return;
    }
    setSent(true);
    toast.success("Password reset email sent.");
  }

  if (sent) {
    return (
      <p className="text-muted-foreground text-center text-sm text-balance">
        If an account exists for{" "}
        <span className="text-foreground">{email}</span>, a reset link is on its
        way.
      </p>
    );
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
      <button
        type="submit"
        disabled={submitting}
        className={cn(buttonVariants({ size: "lg" }), "h-11 w-full text-base")}
      >
        {submitting ? "Sending…" : "Send reset link"}
      </button>
    </form>
  );
}

export default function ForgotPasswordPage() {
  return (
    <AuthShell
      title="Reset your password"
      subtitle="We'll email you a secure link to set a new one."
      footer={
        <Link href="/login" className="text-primary hover:underline">
          Back to sign in
        </Link>
      }
    >
      <ForgotForm />
    </AuthShell>
  );
}
