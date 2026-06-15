/**
 * User profile + preferences model.
 *
 * The single typed shape for identity and preferences. Today it's persisted in
 * localStorage; the repository abstraction (see repository.ts) lets this move to
 * a backend `user_profiles` table later with no UI changes. "Future placeholder"
 * flags are prepared here but not yet functional (no feature reads them to act).
 */

export type AssistantPersonality =
  | "concise"
  | "detailed"
  | "coach"
  | "professional"
  | "friendly";

export interface UserProfile {
  /** What GUMMY calls the user. Null until first-run setup. */
  display_name: string | null;
  preferred_language: string;
  timezone: string;
  onboarding_completed: boolean;
  personality: AssistantPersonality | null;

  // ── Future placeholders (prepared, not yet functional) ────────────────────
  voice_enabled: boolean;
  workflow_learning_enabled: boolean;
  multimodal_enabled: boolean;
}

function detectTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function defaultProfile(): UserProfile {
  return {
    display_name: null,
    preferred_language: "en",
    timezone: detectTimezone(),
    onboarding_completed: false,
    personality: null,
    voice_enabled: false,
    workflow_learning_enabled: false,
    multimodal_enabled: false,
  };
}

export const PERSONALITY_OPTIONS: {
  value: AssistantPersonality;
  label: string;
  description: string;
}[] = [
  { value: "concise", label: "Concise", description: "Short, to the point." },
  {
    value: "detailed",
    label: "Detailed",
    description: "Thorough and complete.",
  },
  { value: "coach", label: "Coach", description: "Motivating and supportive." },
  {
    value: "professional",
    label: "Professional",
    description: "Formal and precise.",
  },
  { value: "friendly", label: "Friendly", description: "Warm and casual." },
];

export const LANGUAGE_OPTIONS = [
  { value: "en", label: "English" },
  { value: "es", label: "Español" },
  { value: "fr", label: "Français" },
  { value: "de", label: "Deutsch" },
  { value: "hi", label: "हिन्दी" },
  { value: "pt", label: "Português" },
  { value: "ar", label: "العربية" },
  { value: "zh", label: "中文" },
];
