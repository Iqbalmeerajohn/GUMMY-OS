"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bell, LogOut, Rocket, Settings, User } from "lucide-react";

import { useAuth } from "@/components/auth/AuthProvider";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useProfile } from "@/lib/profile/useProfile";

/** Top-right identity menu: Profile · Settings · Future Vision · Sign out. */
export function ProfileMenu() {
  const router = useRouter();
  const { user, signOut } = useAuth();
  const { data: profile } = useProfile();

  const name = profile?.display_name ?? user?.email?.split("@")[0] ?? "You";
  const initial = name.charAt(0).toUpperCase();

  async function handleSignOut() {
    await signOut();
    router.replace("/login");
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Open account menu"
        className="bg-accent text-accent-foreground ring-primary/30 grid size-9 place-items-center rounded-full text-sm font-semibold ring-1 transition-shadow hover:ring-2"
      >
        {initial}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <div className="flex flex-col px-2 py-1.5">
          <span className="text-foreground text-sm font-medium">{name}</span>
          {user?.email ? (
            <span className="text-muted-foreground truncate text-xs">
              {user.email}
            </span>
          ) : null}
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem render={<Link href="/profile" />}>
          <User />
          Profile
        </DropdownMenuItem>
        <DropdownMenuItem render={<Link href="/settings/profile" />}>
          <Settings />
          Settings
        </DropdownMenuItem>
        <DropdownMenuItem render={<Link href="/future" />}>
          <Rocket />
          Future Vision
        </DropdownMenuItem>
        <DropdownMenuItem render={<Link href="/updates" />}>
          <Bell />
          Updates
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onClick={handleSignOut}>
          <LogOut />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
