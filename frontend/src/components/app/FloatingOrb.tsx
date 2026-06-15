"use client";

import { useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Compass, Mic, MessageSquarePlus, Bell } from "lucide-react";
import { toast } from "sonner";

import { LivingOrb } from "@/components/brand/LivingOrb";

interface QuickAction {
  label: string;
  icon: typeof Compass;
  href?: string;
  planned?: boolean;
}

const ACTIONS: QuickAction[] = [
  { label: "New Chat", icon: MessageSquarePlus, href: "/workspace" },
  { label: "Voice", icon: Mic, planned: true },
  { label: "Explore GUMMY", icon: Compass, href: "/onboarding" },
  { label: "Updates", icon: Bell, href: "/updates" },
];

/** Mobile-only floating assistant — quick actions, one-handed (bottom-right). */
export function FloatingOrb() {
  const [open, setOpen] = useState(false);
  const reduce = useReducedMotion();

  return (
    <div className="fixed right-4 bottom-20 z-40 flex flex-col items-end gap-2 md:hidden">
      <AnimatePresence>
        {open ? (
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 8, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? undefined : { opacity: 0, y: 8, scale: 0.96 }}
            className="glass elevation-3 flex w-52 flex-col gap-1 rounded-2xl p-2"
          >
            {ACTIONS.map((a) => {
              const Icon = a.icon;
              const content = (
                <span className="hover:bg-accent flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm">
                  <Icon className="text-primary size-4" />
                  {a.label}
                </span>
              );
              return a.href && !a.planned ? (
                <Link
                  key={a.label}
                  href={a.href}
                  onClick={() => setOpen(false)}
                >
                  {content}
                </Link>
              ) : (
                <button
                  key={a.label}
                  onClick={() => {
                    setOpen(false);
                    toast.info(`${a.label} is planned — coming to GUMMY soon.`);
                  }}
                  className="text-left"
                >
                  {content}
                </button>
              );
            })}
          </motion.div>
        ) : null}
      </AnimatePresence>

      <button
        aria-label="GUMMY quick actions"
        onClick={() => setOpen((o) => !o)}
        className="gummy-glow size-14 rounded-full"
      >
        <LivingOrb size={56} state={open ? "thinking" : "idle"} />
      </button>
    </div>
  );
}
