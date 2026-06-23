"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Brain,
  FileText,
  Home,
  MessageSquare,
  Target,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

// Profile is reachable on mobile via the header avatar menu, so the bottom bar
// leads with the primary work surfaces (Goals is the M5 headline feature).
const TABS: { href: string; label: string; icon: LucideIcon }[] = [
  { href: "/dashboard", label: "Home", icon: Home },
  { href: "/workspace", label: "Chat", icon: MessageSquare },
  { href: "/memories", label: "Memory", icon: Brain },
  { href: "/goals", label: "Goals", icon: Target },
  { href: "/files", label: "Files", icon: FileText },
  { href: "/agents", label: "Agents", icon: Users },
];

/** Mobile-only bottom tab bar — thumb-reachable primary navigation. */
export function BottomNav() {
  const pathname = usePathname();

  return (
    <nav className="glass fixed inset-x-0 bottom-0 z-30 border-t border-white/10 pb-[env(safe-area-inset-bottom)] md:hidden">
      <div className="flex items-stretch justify-around">
        {TABS.map((tab) => {
          const active = pathname.startsWith(tab.href);
          const Icon = tab.icon;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] font-medium transition-colors",
                active ? "text-primary" : "text-muted-foreground",
              )}
            >
              <Icon className="size-5" />
              {tab.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
