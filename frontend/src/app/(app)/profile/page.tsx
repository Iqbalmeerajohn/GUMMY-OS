"use client";

import Link from "next/link";
import { Pencil } from "lucide-react";

import { useAuth } from "@/components/auth/AuthProvider";
import { LivingOrb } from "@/components/brand/LivingOrb";
import { Reveal } from "@/components/motion/Reveal";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { buttonVariants } from "@/components/ui/button";
import { useProfile } from "@/lib/profile/useProfile";
import { useRecentConversations } from "@/lib/hooks/useDashboard";
import {
  LANGUAGE_OPTIONS,
  PERSONALITY_OPTIONS,
  type UserProfile,
} from "@/lib/profile/types";
import { formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="glass elevation-2 rounded-2xl p-5 sm:p-6">
      <h2 className="text-muted-foreground mb-4 text-xs font-medium tracking-[0.15em] uppercase">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2.5">
      <dt className="text-muted-foreground text-sm">{label}</dt>
      <dd className="text-sm font-medium">{value}</dd>
    </div>
  );
}

function ProfileView({ profile }: { profile: UserProfile }) {
  const { user } = useAuth();
  const activity = useRecentConversations();

  const personality =
    PERSONALITY_OPTIONS.find((p) => p.value === profile.personality)?.label ??
    "Not set";
  const language =
    LANGUAGE_OPTIONS.find((l) => l.value === profile.preferred_language)
      ?.label ?? profile.preferred_language;
  const created = user?.created_at
    ? new Date(user.created_at).toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : "—";

  const items = activity.data?.items ?? [];

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Reveal className="flex flex-col items-center gap-4 py-2 text-center">
        <LivingOrb size={88} state="idle" />
        <div>
          <h1 className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
            {profile.display_name ?? "Your Profile"}
          </h1>
          {user?.email ? (
            <p className="text-muted-foreground mt-1 text-sm">{user.email}</p>
          ) : null}
        </div>
        <Link
          href="/settings/profile"
          className={cn(
            buttonVariants({ variant: "outline", size: "sm" }),
            "gap-1.5",
          )}
        >
          <Pencil className="size-3.5" />
          Edit profile
        </Link>
      </Reveal>

      <Reveal delay={0.05}>
        <Card title="Identity">
          <dl className="divide-border/50 divide-y">
            <Row label="Display Name" value={profile.display_name ?? "—"} />
            <Row label="Email" value={user?.email ?? "—"} />
            <Row label="Account Created" value={created} />
            <Row label="Assistant Personality" value={personality} />
            <Row label="Timezone" value={profile.timezone} />
            <Row label="Language" value={language} />
            <div className="flex items-center justify-between gap-3 py-2.5">
              <dt className="text-muted-foreground text-sm">Profile Picture</dt>
              <Badge variant="secondary" className="text-[10px]">
                Planned
              </Badge>
            </div>
          </dl>
        </Card>
      </Reveal>

      <Reveal delay={0.1}>
        <Card title="Recent Activity">
          {activity.isLoading ? (
            <Skeleton className="h-16 w-full rounded-lg" />
          ) : activity.isError || items.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              No recent activity yet.
            </p>
          ) : (
            <ul className="space-y-2.5">
              {items.slice(0, 5).map((c) => (
                <li
                  key={c.id}
                  className="border-border/50 bg-background/40 flex items-center justify-between gap-2 rounded-lg border p-2.5"
                >
                  <span className="line-clamp-1 text-sm">
                    {c.title ?? "Untitled conversation"}
                  </span>
                  <span className="text-muted-foreground shrink-0 text-xs">
                    {formatRelativeTime(c.last_message_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </Reveal>
    </div>
  );
}

export default function ProfilePage() {
  const { data: profile } = useProfile();
  return profile ? (
    <ProfileView profile={profile} />
  ) : (
    <div className="mx-auto max-w-2xl">
      <Skeleton className="h-72 w-full rounded-2xl" />
    </div>
  );
}
