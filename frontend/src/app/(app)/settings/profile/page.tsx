"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth/AuthProvider";
import { Reveal } from "@/components/motion/Reveal";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { buttonVariants } from "@/components/ui/button";
import { useProfile, useUpdateProfile } from "@/lib/profile/useProfile";
import { LANGUAGE_OPTIONS, type UserProfile } from "@/lib/profile/types";
import { analytics, AnalyticsEvent } from "@/lib/analytics";
import { cn } from "@/lib/utils";

const FEATURES_ENABLED = ["Memory System", "Goals System", "Agent System"];

const selectClass =
  "border-input h-9 w-full rounded-lg border bg-transparent px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

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

function timezones(): string[] {
  try {
    const fn = (
      Intl as unknown as { supportedValuesOf?: (k: string) => string[] }
    ).supportedValuesOf;
    if (fn) return fn("timeZone");
  } catch {
    /* fall through */
  }
  return ["UTC", "America/New_York", "Europe/London", "Asia/Kolkata"];
}

/** Editable form — mounted only once the profile is loaded, so state can
 *  initialize from props without an effect (and without hydration mismatch). */
function SettingsForm({ profile }: { profile: UserProfile }) {
  const { user } = useAuth();
  const update = useUpdateProfile();

  const [displayName, setDisplayName] = useState(profile.display_name ?? "");
  const [timezone, setTimezone] = useState(profile.timezone);
  const [language, setLanguage] = useState(profile.preferred_language);

  async function onSave() {
    if (!displayName.trim()) {
      toast.error("Display name can't be empty.");
      return;
    }
    await update.mutateAsync({
      display_name: displayName.trim(),
      timezone,
      preferred_language: language,
    });
    analytics.track(AnalyticsEvent.ProfileUpdated, {
      fields: ["display_name", "timezone", "preferred_language"],
    });
    toast.success("Profile updated.");
  }

  const created = user?.created_at
    ? new Date(user.created_at).toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : "—";

  return (
    <>
      <Reveal delay={0.05}>
        <Card title="Profile">
          <div className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="displayName">Display Name</Label>
              <Input
                id="displayName"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                maxLength={60}
                placeholder="e.g. Iqbal"
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="timezone">Timezone</Label>
                <select
                  id="timezone"
                  className={selectClass}
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                >
                  {timezones().map((tz) => (
                    <option key={tz} value={tz}>
                      {tz}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="language">Preferred Language</Label>
                <select
                  id="language"
                  className={selectClass}
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                >
                  {LANGUAGE_OPTIONS.map((l) => (
                    <option key={l.value} value={l.value}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <button
              onClick={onSave}
              disabled={update.isPending}
              className={cn(buttonVariants({ size: "lg" }), "h-10")}
            >
              {update.isPending ? "Saving…" : "Save Changes"}
            </button>
          </div>
        </Card>
      </Reveal>

      <Reveal delay={0.1}>
        <Card title="Account">
          <dl className="divide-border/50 divide-y text-sm">
            <div className="flex items-center justify-between py-2.5">
              <dt className="text-muted-foreground">Name</dt>
              <dd className="font-medium">{displayName || "—"}</dd>
            </div>
            <div className="flex items-center justify-between py-2.5">
              <dt className="text-muted-foreground">Email</dt>
              <dd className="font-medium">{user?.email ?? "—"}</dd>
            </div>
            <div className="flex items-center justify-between py-2.5">
              <dt className="text-muted-foreground">Account Created</dt>
              <dd className="font-medium">{created}</dd>
            </div>
          </dl>
        </Card>
      </Reveal>

      <Reveal delay={0.12}>
        <Card title="Features Enabled">
          <div className="grid gap-2.5 sm:grid-cols-3">
            {FEATURES_ENABLED.map((f) => (
              <div
                key={f}
                className="border-border/50 bg-background/40 flex items-center gap-2 rounded-xl border p-3"
              >
                <span className="bg-primary text-primary-foreground grid size-5 shrink-0 place-items-center rounded-full">
                  <Check className="size-3" />
                </span>
                <span className="text-sm font-medium">{f}</span>
              </div>
            ))}
          </div>
        </Card>
      </Reveal>
    </>
  );
}

export default function ProfileSettingsPage() {
  const { data: profile } = useProfile();

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Reveal>
        <h1 className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
          Profile &amp; Settings
        </h1>
      </Reveal>

      {profile ? (
        <SettingsForm profile={profile} />
      ) : (
        <Skeleton className="h-64 w-full rounded-2xl" />
      )}
    </div>
  );
}
