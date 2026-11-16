import { Timeline } from "@/components/profile/Timeline";
import type { Dictionary } from "@/lib/i18n/config";
import type { Profile } from "@/services/types";

import { CardFooterLink } from "./CardFooterLink";

export function ExperienceCard({ profile, t }: { profile: Profile; t: Dictionary }) {
  if (!profile.experience) return null;
  return (
    <>
      <Timeline title={profile.experience.title} items={profile.experience.sections} />
      <CardFooterLink href="/about#experience" label={t.cards.aboutLink} />
    </>
  );
}
