"use client";

import { useState } from "react";
import { CalendarPlus, LogOut } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth/AuthProvider";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { buttonVariants } from "@/components/ui/button";
import { importCalendar } from "@/lib/api/resources";
import { useProfile, useUpdateProfile } from "@/lib/profile/useProfile";
import { LANGUAGE_OPTIONS, type UserProfile } from "@/lib/profile/types";
import { analytics, AnalyticsEvent } from "@/lib/analytics";
import { cn } from "@/lib/utils";

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
    <section className="glass elevation-2 rounded-2xl p-4">
      <h2 className="text-muted-foreground mb-3 text-xs font-medium tracking-[0.15em] uppercase">
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

/** Import a calendar so Gummy knows what the user actually did, not only what
 *  they typed. The secret iCal address needs no OAuth scopes, which is why this
 *  works on a machine that talks to nothing else. */
function CalendarCard() {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);

  async function onImport() {
    if (!url.startsWith("https://")) {
      toast.error("Paste the https secret iCal address from Google Calendar.");
      return;
    }
    setBusy(true);
    try {
      const result = await importCalendar(url.trim());
      toast.success(
        result.imported
          ? `Imported ${result.imported} past event${result.imported === 1 ? "" : "s"}.`
          : "Nothing new to import.",
      );
      setUrl("");
    } catch {
      toast.error("That calendar couldn't be reached.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Connected sources">
      <div className="space-y-3">
        <div className="space-y-2">
          <Label htmlFor="ics">Google Calendar (secret iCal address)</Label>
          <Input
            id="ics"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://calendar.google.com/calendar/ical/…/basic.ics"
          />
          <p className="text-muted-foreground text-xs">
            Calendar settings → Secret address in iCal format. Past events
            become memories; nothing leaves your machine.
          </p>
        </div>
        <button
          onClick={onImport}
          disabled={busy}
          className={cn(
            buttonVariants({ variant: "outline" }),
            "h-9 w-full gap-2",
          )}
        >
          <CalendarPlus className="size-3.5" />
          {busy ? "Importing…" : "Import calendar"}
        </button>
      </div>
    </Card>
  );
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
      <Card title="You">
        <div className="space-y-4">
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

          <button
            onClick={onSave}
            disabled={update.isPending}
            className={cn(buttonVariants({ size: "lg" }), "h-10 w-full")}
          >
            {update.isPending ? "Saving…" : "Save Changes"}
          </button>
        </div>
      </Card>

      <CalendarCard />

      <Card title="Account">
        <dl className="divide-border/50 divide-y text-sm">
          <div className="flex items-center justify-between gap-3 py-2.5">
            <dt className="text-muted-foreground">Email</dt>
            <dd className="truncate font-medium">{user?.email ?? "—"}</dd>
          </div>
          <div className="flex items-center justify-between gap-3 py-2.5">
            <dt className="text-muted-foreground">Member since</dt>
            <dd className="font-medium">{created}</dd>
          </div>
          <div className="flex items-center justify-between gap-3 py-2.5">
            <dt className="text-muted-foreground">Data</dt>
            <dd className="font-medium">Stored on this machine</dd>
          </div>
        </dl>
      </Card>
    </>
  );
}

/** Profile + account settings, as a panel. */
export function SettingsPanel() {
  const { data: profile } = useProfile();
  const { signOut } = useAuth();

  return (
    <div className="h-full min-h-0 space-y-3 overflow-y-auto p-4">
      {profile ? (
        <SettingsForm profile={profile} />
      ) : (
        <Skeleton className="h-64 w-full rounded-2xl" />
      )}
      <button
        onClick={async () => {
          analytics.track(AnalyticsEvent.UserLoggedOut);
          await signOut();
        }}
        className={cn(
          buttonVariants({ variant: "outline", size: "sm" }),
          "w-full gap-2",
        )}
      >
        <LogOut className="size-3.5" />
        Sign out
      </button>
    </div>
  );
}
