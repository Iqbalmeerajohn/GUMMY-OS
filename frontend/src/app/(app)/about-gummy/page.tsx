import type { Metadata } from "next";

import { LivingOrb } from "@/components/brand/LivingOrb";
import { Reveal } from "@/components/motion/Reveal";

export const metadata: Metadata = {
  title: "About GUMMY",
};

const POSITIONING = [
  "GUMMY remembers.",
  "GUMMY plans.",
  "GUMMY executes.",
  "GUMMY learns workflows.",
  "GUMMY becomes a personal operating system.",
];

function Block({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Reveal className="glass elevation-2 rounded-2xl p-6 sm:p-8">
      <h2 className="font-heading text-xl font-semibold tracking-tight">
        {title}
      </h2>
      <div className="text-muted-foreground mt-3 space-y-3 text-balance">
        {children}
      </div>
    </Reveal>
  );
}

/** About GUMMY — what it is, why it exists, how it's different. */
export default function AboutGummyPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <Reveal className="flex flex-col items-center gap-6 py-4 text-center">
        <LivingOrb size={120} state="idle" />
        <h1 className="font-heading text-4xl font-semibold tracking-tight sm:text-5xl">
          About GUMMY
        </h1>
      </Reveal>

      <Block title="What GUMMY Is">
        <p>
          GUMMY is a Personal AI Operating System — a unified layer for your
          knowledge, goals, memory, and execution. Chat is one tool inside it,
          not the whole experience.
        </p>
      </Block>

      <Block title="Why GUMMY Exists">
        <p>
          Most AI systems answer questions and forget the moment the
          conversation ends. GUMMY exists to remember context, understand what
          you&apos;re trying to achieve, and help you make progress over time.
        </p>
      </Block>

      <Block title="How It Is Different">
        <p>Most AI systems answer questions.</p>
        <ul className="space-y-2">
          {POSITIONING.map((line) => (
            <li key={line} className="flex items-center gap-2.5">
              <span className="bg-primary size-1.5 rounded-full" />
              <span className="text-foreground font-medium">{line}</span>
            </li>
          ))}
        </ul>
      </Block>
    </div>
  );
}
