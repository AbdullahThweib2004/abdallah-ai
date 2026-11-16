import { Timeline } from "@/components/profile/Timeline";
import type { Dictionary } from "@/lib/i18n/config";
import type { Profile } from "@/services/types";

import { CardFooterLink } from "./CardFooterLink";

export function EducationCard({ profile, t }: { profile: Profile; t: Dictionary }) {
  return (
    <>
      <Timeline items={profile.education} />
      <CardFooterLink href="/about#education" label={t.cards.aboutLink} />
    </>
  );
}
