"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search } from "lucide-react";

import { LivingOrb } from "@/components/brand/LivingOrb";
import { ProfileMenu } from "@/components/app/ProfileMenu";
import { OrbNotification } from "@/components/app/OrbNotification";
import { IdentitySync } from "@/components/auth/IdentitySync";
import { useHideOnScroll } from "@/lib/hooks/useScrollDirection";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/workspace", label: "Workspace" },
  { href: "/memories", label: "Memory" },
  { href: "/goals", label: "Goals" },
  { href: "/files", label: "Files" },
  { href: "/agents", label: "Agents" },
  { href: "/future", label: "Future Vision" },
  { href: "/updates", label: "Updates" },
] as const;

/** Shared top bar — desktop nav inline; mobile relies on the bottom nav.
 *  Auto-hides on scroll-down, reveals on scroll-up (iPhone-style). */
export function AppHeader() {
  const pathname = usePathname();
  const hidden = useHideOnScroll();

  return (
    <header
      className={cn(
        "glass sticky top-0 z-30 border-b border-white/10 transition-transform duration-300",
        hidden ? "-translate-y-full" : "translate-y-0",
      )}
    >
      <IdentitySync />
      <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-5 py-3">
        <div className="flex items-center gap-6">
          <Link href="/dashboard" className="flex items-center gap-2.5">
            <LivingOrb size={30} state="idle" />
            <span className="font-heading text-lg font-semibold tracking-tight">
              GUMMY
            </span>
          </Link>
          <nav className="hidden items-center gap-1 md:flex">
            {NAV.map((item) => {
              const active = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-sm whitespace-nowrap transition-colors",
                    active
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="flex items-center gap-1.5">
          <Link
            href="/search"
            aria-label="Search"
            className={cn(
              "text-muted-foreground hover:bg-accent hover:text-foreground grid size-10 place-items-center rounded-lg transition-colors",
              pathname.startsWith("/search") && "bg-accent text-foreground",
            )}
          >
            <Search className="size-5" />
          </Link>
          <OrbNotification />
          <ProfileMenu />
        </div>
      </div>
    </header>
  );
}
