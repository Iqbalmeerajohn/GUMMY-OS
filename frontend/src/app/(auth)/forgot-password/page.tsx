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
        title="Check your email"
        subtitle="If an account exists for that address, a password reset link is on its way."
        footer={
          <Link href="/login" className="hover:text-foreground underline">
            Back to sign in
          </Link>
        }
      >
        <div className="space-y-4">
          <p className="text-muted-foreground text-sm">
            The link works once and expires shortly. If it doesn&apos;t arrive,
            check your spam folder or try again.
          </p>

          {consoleMode ? (
            <p className="border-primary/20 bg-primary/5 text-muted-foreground rounded-xl border p-3 text-xs">
              <span className="text-foreground font-medium">
                Local development:
              </span>{" "}
              this server logs auth email instead of sending it. The reset link
              is in the backend console, tagged{" "}
              <code className="text-foreground">[GUMMY AUTH]</code>.
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
