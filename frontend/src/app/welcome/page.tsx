"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { LivingOrb } from "@/components/brand/LivingOrb";
import { Reveal } from "@/components/motion/Reveal";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { buttonVariants } from "@/components/ui/button";
import { useProfile, useUpdateProfile } from "@/lib/profile/useProfile";
import {
  PERSONALITY_OPTIONS,
  type AssistantPersonality,
} from "@/lib/profile/types";
import { cn } from "@/lib/utils";

/**
 * First-run identity setup: what GUMMY should call you + the assistant's
 * personality. Persisted to the profile; then into the dashboard.
 */
export default function WelcomePage() {
  const router = useRouter();
  const { data: profile } = useProfile();
  const update = useUpdateProfile();
  const [name, setName] = useState("");
  const [personality, setPersonality] = useState<AssistantPersonality | null>(
    null,
  );

  // Prefill once profile loads (e.g. returning to edit).
  const displayName = name || profile?.display_name || "";

  async function onContinue() {
    const trimmed = displayName.trim();
    if (!trimmed) {
      toast.error("Please tell GUMMY what to call you.");
      return;
    }
    await update.mutateAsync({
      display_name: trimmed,
      personality: personality ?? profile?.personality ?? "friendly",
    });
    router.replace("/dashboard");
  }

  return (
    <div className="flex min-h-[100svh] flex-col items-center justify-center px-6 py-12">
      <Reveal className="flex flex-col items-center">
        <LivingOrb size={96} state="listening" className="mb-8" />
      </Reveal>

      <Reveal delay={0.08} className="w-full max-w-md text-center">
        <h1 className="font-heading text-3xl font-semibold tracking-tight sm:text-4xl">
          Welcome to GUMMY
        </h1>
        <p className="text-muted-foreground mt-2">
          A couple of quick things to make GUMMY yours.
        </p>
      </Reveal>

      <Reveal delay={0.14} className="mt-8 w-full max-w-md space-y-6">
        <div className="space-y-2">
          <Label htmlFor="name">What should GUMMY call you?</Label>
          <Input
            id="name"
            autoFocus
            value={displayName}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Iqbal"
            maxLength={60}
          />
        </div>

        <div className="space-y-3">
          <Label>What kind of assistant should GUMMY be?</Label>
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
            {PERSONALITY_OPTIONS.map((opt) => {
              const active =
                (personality ?? profile?.personality) === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setPersonality(opt.value)}
                  className={cn(
                    "rounded-xl border p-3 text-left transition-colors",
                    active
                      ? "border-primary bg-accent"
                      : "border-border/60 hover:border-primary/40",
                  )}
                >
                  <span className="text-sm font-medium">{opt.label}</span>
                  <span className="text-muted-foreground mt-0.5 block text-xs">
                    {opt.description}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <button
          onClick={onContinue}
          disabled={update.isPending}
          className={cn(
            buttonVariants({ size: "lg" }),
            "gummy-glow h-11 w-full text-base",
          )}
        >
          {update.isPending ? "Saving…" : "Enter GUMMY"}
        </button>
      </Reveal>
    </div>
  );
}
