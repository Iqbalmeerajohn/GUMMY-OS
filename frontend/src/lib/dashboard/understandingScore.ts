/**
 * User Understanding Score — how well GUMMY knows the user, on a 0–100 scale.
 *
 * Pure and self-contained (no imports), so it is trivially unit-testable and
 * carries no React/runtime coupling. Every input is real profile + memory +
 * goal/activity data assembled by `useUnderstandingScore`; there are no demo or
 * hardcoded percentages here — the numbers below are the scoring *rules*, not
 * fabricated values.
 *
 * Ten criteria, 10 points each (total 100):
 *   Name · Career · Education · Skills · Projects · Preferences · Location ·
 *   Goals · Recent activity · Memory maturity
 *
 * Most criteria map to a strong signal (a profile field, a memory category, or
 * a backend count). Education / Skills / Location have no dedicated memory
 * category, so they are detected from real memory *content* via keyword vocab.
 * Memory maturity is graded: 1 point per active memory up to the target.
 */

/** Real, already-fetched data the score reads. */
export interface UnderstandingInput {
  /** Profile display name (from the user's saved profile). */
  displayName: string | null;
  /** Active memory contents — scanned for education/skills/location signals. */
  memoryContents: string[];
  /** Count of active memories per category (career, project, preference, …). */
  memoriesByCategory: Record<string, number>;
  /** Total active memory count — drives maturity + the "teach me more" hint. */
  memoryCount: number;
  /** Active goals tracked by the backend. */
  activeGoalsCount: number;
  /** Recent conversations — the activity signal. */
  recentActivityCount: number;
}

/** One scored line: met/unmet plus the points it contributed. */
export interface ScoreCriterion {
  key: string;
  label: string;
  met: boolean;
  earned: number;
  max: number;
}

export interface UnderstandingScore {
  /** 0–100, the sum of all earned points. */
  score: number;
  criteria: ScoreCriterion[];
  /** True when the user has fewer than the minimum memories to personalize. */
  needsMoreData: boolean;
}

/** Points awarded per fully-met criterion. */
export const CRITERION_POINTS = 10;
/** Below this many active memories, prompt the user to teach GUMMY more. */
export const MIN_MEMORIES_FOR_PERSONALIZATION = 5;
/** Active memories needed for full memory-maturity points. */
export const MATURITY_TARGET = 10;

// Detection vocabularies for the criteria without a dedicated memory category.
// These are matchers over real memory content, not user data.
const EDUCATION_KEYWORDS = [
  "education",
  "studied",
  "study",
  "university",
  "college",
  "school",
  "degree",
  "bachelor",
  "master",
  "phd",
  "graduated",
  "major",
  "diploma",
  "alma mater",
];
const SKILL_KEYWORDS = [
  "skill",
  "proficient",
  "experienced",
  "expert",
  "fluent",
  "programming",
  "developer",
  "engineer",
  "certified",
  "framework",
  "specializes",
  "knows how",
];
const LOCATION_KEYWORDS = [
  "live in",
  "lives in",
  "based in",
  "located in",
  "location",
  "city",
  "country",
  "reside",
  "hometown",
  "address",
];
const CAREER_KEYWORDS = [
  "career",
  "job",
  "role",
  "position",
  "company",
  "profession",
  "targeting",
  "applying",
  "employer",
  "hiring",
];
const PROJECT_KEYWORDS = [
  "project",
  "building",
  "developing",
  "launching",
  "shipping",
  "startup",
];

function anyContains(contents: string[], keywords: string[]): boolean {
  return contents.some((raw) => {
    const text = raw.toLowerCase();
    return keywords.some((kw) => text.includes(kw));
  });
}

/** Compute the User Understanding Score from real profile + memory data. */
export function computeUnderstandingScore(
  input: UnderstandingInput,
): UnderstandingScore {
  const has = (category: string): boolean =>
    (input.memoriesByCategory[category] ?? 0) > 0;
  const contents = input.memoryContents;

  const nameKnown =
    Boolean(input.displayName && input.displayName.trim()) || has("profile");
  const careerKnown = has("career") || anyContains(contents, CAREER_KEYWORDS);
  const educationKnown = anyContains(contents, EDUCATION_KEYWORDS);
  const skillsKnown = anyContains(contents, SKILL_KEYWORDS);
  const projectsKnown =
    has("project") || anyContains(contents, PROJECT_KEYWORDS);
  const preferencesKnown = has("preference");
  const locationKnown = anyContains(contents, LOCATION_KEYWORDS);
  const goalsKnown = input.activeGoalsCount > 0;
  const activityKnown = input.recentActivityCount > 0;

  const booleanCriteria: ReadonlyArray<[string, string, boolean]> = [
    ["name", "Name", nameKnown],
    ["career", "Career", careerKnown],
    ["education", "Education", educationKnown],
    ["skills", "Skills", skillsKnown],
    ["projects", "Projects", projectsKnown],
    ["preferences", "Preferences", preferencesKnown],
    ["location", "Location", locationKnown],
    ["goals", "Goals", goalsKnown],
    ["activity", "Recent activity", activityKnown],
  ];

  const criteria: ScoreCriterion[] = booleanCriteria.map(
    ([key, label, met]) => ({
      key,
      label,
      met,
      earned: met ? CRITERION_POINTS : 0,
      max: CRITERION_POINTS,
    }),
  );

  // Memory maturity: graded 1 point per active memory up to the target.
  const maturityEarned = Math.min(
    CRITERION_POINTS,
    Math.round(
      (Math.min(input.memoryCount, MATURITY_TARGET) / MATURITY_TARGET) *
        CRITERION_POINTS,
    ),
  );
  criteria.push({
    key: "maturity",
    label: "Memory maturity",
    met: input.memoryCount >= MATURITY_TARGET,
    earned: maturityEarned,
    max: CRITERION_POINTS,
  });

  const score = criteria.reduce((sum, c) => sum + c.earned, 0);

  return {
    score,
    criteria,
    needsMoreData: input.memoryCount < MIN_MEMORIES_FOR_PERSONALIZATION,
  };
}
