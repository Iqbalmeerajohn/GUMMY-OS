import type { ReactNode } from "react";

import { AppHeader } from "@/components/app/AppHeader";
import { BottomNav } from "@/components/app/BottomNav";
import { FloatingOrb } from "@/components/app/FloatingOrb";

/** Shared chrome for centered authenticated routes (dashboard, future, etc.). */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-[100svh] flex-col">
      <AppHeader />
      {/* Extra bottom padding on mobile to clear the bottom nav. */}
      <main className="mx-auto w-full max-w-6xl flex-1 px-5 pt-8 pb-28 md:pb-8">
        {children}
      </main>
      <BottomNav />
      <FloatingOrb />
    </div>
  );
}
