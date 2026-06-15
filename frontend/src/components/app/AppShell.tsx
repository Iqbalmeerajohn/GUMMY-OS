import type { ReactNode } from "react";

import { AppHeader } from "@/components/app/AppHeader";

/** Shared chrome for centered authenticated routes (dashboard, future, etc.). */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-[100svh] flex-col">
      <AppHeader />
      <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-8">
        {children}
      </main>
    </div>
  );
}
