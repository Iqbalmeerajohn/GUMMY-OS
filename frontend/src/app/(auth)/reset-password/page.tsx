"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";

import { AuthShell } from "@/components/auth/AuthShell";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { buttonVariants } from "@/components/ui/button";
import {
  MIN_PASSWORD_LENGTH,
  validateNewPassword,
} from "@/lib/auth/passwordPolicy";
import { resetPassword } from "@/lib/auth/session";
import { cn } from "@/lib/utils";

function ResetPasswordForm() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const problem = validateNewPassword(password, confirm);
    if (problem) {
      toast.error(problem);
      return;
    }
    setSubmitting(true);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Something went wrong. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  // No token in the URL at all — someone opened the page directly. Say so
  // rather than rendering a form whose only possible outcome is a 400.
  if (!token) {
    return (
      <div className="space-y-4">
        <p className="text-muted-foreground text-sm">
          This page needs a reset link. Request a new one and open the link from
          your email.
        </p>
        <Link
          href="/forgot-password"
          className={cn(buttonVariants(), "w-full")}
        >
          Request a reset link
        </Link>
      </div>
    );
  }

  if (done) {
    return (
      <div className="space-y-4">
        <p className="text-sm">Your password has been reset successfully.</p>
        <p className="text-muted-foreground text-sm">
          For your security, any other devices signed in to this account have
          been signed out.
        </p>
        <Link href="/login" className={cn(buttonVariants(), "w-full")}>
          Continue to sign in
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="password">New password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="confirm">Confirm password</Label>
        <Input
          id="confirm"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="••••••••"
        />
      </div>
      <button
        type="submit"
        disabled={submitting}
        className={cn(buttonVariants(), "w-full")}
      >
        {submitting ? "Resetting…" : "Reset password"}
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <AuthShell
      title="Set a new password"
      subtitle="Choose a password you don't use anywhere else."
      footer={
        <Link href="/login" className="hover:text-foreground underline">
          Back to sign in
        </Link>
      }
    >
      {/* `useSearchParams` reads the token, so it needs a Suspense boundary —
          same shape as the login and signup pages. */}
      <Suspense fallback={null}>
        <ResetPasswordForm />
      </Suspense>
    </AuthShell>
  );
}
