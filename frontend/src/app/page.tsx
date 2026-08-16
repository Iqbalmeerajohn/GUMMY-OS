"use client";

import { useAuth } from "@/components/auth/AuthProvider";
import { LandingHero } from "@/components/brand/LandingHero";
import { LivingOrb } from "@/components/brand/LivingOrb";
import { GummyShell } from "@/components/shell/GummyShell";

/**
 * The entire app lives at `/`.
 *
 * Signed in, this is the chat shell — everything else (memory, goals, files,
 * agents, search, settings) opens as a panel over the same conversation.
 * Signed out, it is the landing page.
 */
export default function Home() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="grid h-[100svh] place-items-center">
        <LivingOrb size={64} state="thinking" />
      </div>
    );
  }

  return user ? <GummyShell /> : <LandingHero />;
}
