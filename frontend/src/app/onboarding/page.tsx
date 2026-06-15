import type { Metadata } from "next";

import { OnboardingFlow } from "@/components/onboarding/OnboardingFlow";

export const metadata: Metadata = {
  title: "Welcome",
};

/**
 * The guided onboarding journey (public — also the landing "Learn More" tour).
 * Finishing routes signed-in users to the dashboard, or to signup otherwise.
 */
export default function OnboardingPage() {
  return <OnboardingFlow />;
}
