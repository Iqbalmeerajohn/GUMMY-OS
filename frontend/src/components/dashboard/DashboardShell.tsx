"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import type { ReactNode } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { LivingOrb } from "@/components/brand/LivingOrb";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Protected app chrome: a slim top bar + content area. */
export function DashboardShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { user, signOut } = useAuth();

  async function handleSignOut() {
    await signOut();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-[100svh] flex-col">
      <header className="glass sticky top-0 z-30 border-b border-white/10">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-3">
          <Link href="/dashboard" className="flex items-center gap-2.5">
            <LivingOrb size={30} state="idle" />
            <span className="font-heading text-lg font-semibold tracking-tight">
              GUMMY
            </span>
          </Link>
          <div className="flex items-center gap-3">
            {user?.email ? (
              <span className="text-muted-foreground hidden text-sm sm:inline">
                {user.email}
              </span>
            ) : null}
            <button
              onClick={handleSignOut}
              className={cn(
                buttonVariants({ variant: "outline", size: "sm" }),
                "gap-1.5",
              )}
            >
              <LogOut className="size-3.5" />
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-8">
        {children}
      </main>
    </div>
  );
}
