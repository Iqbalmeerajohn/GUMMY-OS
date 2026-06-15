import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { HeroOrb } from "@/components/brand/HeroOrb";
import { Reveal } from "@/components/motion/Reveal";
import { Stagger, StaggerItem } from "@/components/motion/Stagger";
import { cn } from "@/lib/utils";

const ctaBase = "h-11 px-6 text-base w-full sm:w-auto";

const PILLARS = ["Memory", "Goals", "Agents", "Automation"];

/**
 * Landing hero (M0.75). Premium, mobile-first first impression that states what
 * GUMMY is. The full landing / onboarding lands in M2; CTAs route into the M1
 * auth flow (/signup) and the M2 Discover page (/discover).
 */
export default function Home() {
  return (
    <main className="relative flex flex-1 flex-col items-center justify-center gap-6 overflow-x-hidden px-6 py-10 text-center sm:gap-10 sm:py-16">
      <Reveal>
        <HeroOrb />
      </Reveal>

      {/* Wordmark + positioning label. */}
      <Reveal delay={0.08} className="flex flex-col items-center gap-3">
        <h1 className="font-heading bg-gradient-to-b from-white to-white/55 bg-clip-text text-6xl font-bold tracking-tight text-transparent sm:text-7xl md:text-8xl">
          GUMMY
        </h1>
        <p className="text-primary/85 text-xs font-medium tracking-[0.28em] uppercase sm:text-sm">
          Your Personal AI Operating System
        </p>
      </Reveal>

      {/* The four pillars — punchy display sequence. */}
      <Stagger className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
        {PILLARS.map((word) => (
          <StaggerItem key={word}>
            <span className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl md:text-4xl">
              {word}
              <span className="text-primary">.</span>
            </span>
          </StaggerItem>
        ))}
      </Stagger>

      <Reveal delay={0.12}>
        <p className="text-muted-foreground max-w-md text-base text-balance sm:text-lg">
          One intelligence layer for everything.
        </p>
      </Reveal>

      {/* Calls to action — connect into M1 auth. */}
      <Reveal
        delay={0.16}
        className="flex w-full flex-col items-center justify-center gap-3 sm:w-auto sm:flex-row"
      >
        <Link
          href="/signup"
          className={cn(buttonVariants({ size: "lg" }), ctaBase, "gummy-glow")}
        >
          Get Started
        </Link>
        <Link
          href="/onboarding"
          className={cn(
            buttonVariants({ variant: "outline", size: "lg" }),
            ctaBase,
            "glass",
          )}
        >
          Learn More
        </Link>
      </Reveal>
    </main>
  );
}
