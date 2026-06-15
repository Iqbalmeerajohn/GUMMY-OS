"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ArrowLeft } from "lucide-react";

import { OnboardingVisualView, visualShowsItems } from "./visuals";
import { useAuth } from "@/components/auth/AuthProvider";
import { buttonVariants } from "@/components/ui/button";
import { ONBOARDING_STEPS } from "@/config/onboarding";
import { markOnboardingComplete } from "@/lib/onboarding";
import { cn } from "@/lib/utils";

export function OnboardingFlow() {
  const router = useRouter();
  const { user } = useAuth();
  const reduce = useReducedMotion();
  const [index, setIndex] = useState(0);

  const step = ONBOARDING_STEPS[index];
  const isLast = index === ONBOARDING_STEPS.length - 1;
  const showPills = step.items && !visualShowsItems(step.visual);

  function finish() {
    markOnboardingComplete();
    router.replace(user ? "/dashboard" : "/signup");
  }

  function next() {
    if (isLast) finish();
    else setIndex((i) => i + 1);
  }

  return (
    <div className="relative flex min-h-[100svh] flex-col px-6 py-6">
      {/* Top bar: progress + skip. */}
      <div className="mx-auto flex w-full max-w-3xl items-center justify-between">
        <div className="flex gap-1.5">
          {ONBOARDING_STEPS.map((s, i) => (
            <span
              key={s.id}
              className={cn(
                "h-1 rounded-full transition-all",
                i === index ? "bg-primary w-6" : "bg-muted w-2.5",
              )}
            />
          ))}
        </div>
        <button
          onClick={finish}
          className="text-muted-foreground hover:text-foreground text-sm"
        >
          Skip
        </button>
      </div>

      {/* Step content. */}
      <div className="flex flex-1 items-center justify-center">
        <AnimatePresence mode="wait">
          <motion.div
            key={step.id}
            className="flex w-full max-w-2xl flex-col items-center gap-7 text-center"
            initial={reduce ? false : { opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -16 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          >
            <OnboardingVisualView step={step} />

            <div className="flex flex-col items-center gap-3">
              {step.kicker ? (
                <span className="text-primary/85 text-xs font-medium tracking-[0.2em] uppercase">
                  {step.kicker}
                </span>
              ) : null}
              <h1 className="font-heading text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
                {step.headline}
                {step.highlight ? (
                  <>
                    {" "}
                    <span className="text-primary">{step.highlight}</span>
                  </>
                ) : null}
              </h1>
              <div className="text-muted-foreground max-w-xl space-y-2 text-base text-balance sm:text-lg">
                {step.paragraphs.map((p) => (
                  <p key={p}>{p}</p>
                ))}
              </div>
            </div>

            {showPills ? (
              <div className="flex flex-wrap justify-center gap-2">
                {step.items!.map((item) => (
                  <span
                    key={item.title}
                    className="glass rounded-full px-3.5 py-1.5 text-sm font-medium"
                  >
                    {item.title}
                  </span>
                ))}
              </div>
            ) : null}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Footer: back + primary CTA. */}
      <div className="mx-auto flex w-full max-w-2xl items-center justify-center gap-3">
        {index > 0 ? (
          <button
            onClick={() => setIndex((i) => i - 1)}
            aria-label="Back"
            className={cn(
              buttonVariants({ variant: "outline", size: "lg" }),
              "glass h-11 px-4",
            )}
          >
            <ArrowLeft className="size-4" />
          </button>
        ) : null}
        <button
          onClick={next}
          className={cn(
            buttonVariants({ size: "lg" }),
            "gummy-glow h-11 min-w-44 px-8 text-base",
          )}
        >
          {step.cta}
        </button>
      </div>
    </div>
  );
}
