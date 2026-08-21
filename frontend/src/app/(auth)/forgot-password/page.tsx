"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";

import { AuthShell } from "@/components/auth/AuthShell";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { buttonVariants } from "@/components/ui/button";
import { fetchAuthConfig, requestPasswordReset } from "@/lib/auth/session";
import { cn } from "@/lib/utils";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  // Whether the backend logs the reset link instead of emailing it. Only used
  // to tell a local developer where to look — the success copy itself stays
  // identical either way.
  const [consoleMode, setConsoleMode] = useState(false);

  useEffect(() => {
    fetchAuthConfig()
      .then((config) => setConsoleMode(config.email_console_mode))
      .catch(() => setConsoleMode(false));
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await requestPasswordReset(email);
      // Shown whether or not the address has an account. The backend answers
      // identically on purpose, and the UI must not undo that by rendering
      // two different screens.
      setSent(true);
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

  if (sent) {
    return (
      <AuthShell
        // In console mode nothing was emailed, so "Check your email" would be
        // a plain untruth — and sending someone to an inbox that will never
        // receive anything is a worse dead end than saying so. The wording
        // below still reveals nothing about whether the account exists.
        title={consoleMode ? "Reset link generated" : "Check your email"}
        subtitle={
          consoleMode
            ? "This server logs auth email instead of sending it, so the link is waiting in the backend console."
            : "If an account exists for that address, a password reset link is on its way."
        }
        footer={
          <Link href="/login" className="hover:text-foreground underline">
            Back to sign in
          </Link>
        }
      >
        <div className="space-y-4">
          <p className="text-muted-foreground text-sm">
            {consoleMode
              ? "The link works once and expires shortly, exactly as it would by email."
              : "The link works once and expires shortly. If it doesn't arrive, check your spam folder or try again."}
          </p>

          {consoleMode ? (
            <p className="border-primary/20 bg-primary/5 text-muted-foreground rounded-xl border p-3 text-xs">
              <span className="text-foreground font-medium">
                Local development:
              </span>{" "}
              find it in the backend console, tagged{" "}
              <code className="text-foreground">[GUMMY AUTH]</code>. Set{" "}
              <code className="text-foreground">AUTH_EMAIL_MODE=smtp</code> to
              deliver real email.
            </p>
          ) : null}

          <button
            type="button"
            onClick={() => setSent(false)}
            className={cn(buttonVariants({ variant: "ghost" }), "w-full")}
          >
            Use a different email
          </button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Reset your password"
      subtitle="Enter your email and we'll send you a link to set a new one."
      footer={
        <Link href="/login" className="hover:text-foreground underline">
          Back to sign in
        </Link>
      }
    >
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
          className={cn(buttonVariants(), "w-full")}
        >
          {submitting ? "Sending…" : "Send reset link"}
        </button>
      </form>
    </AuthShell>
  );
}
