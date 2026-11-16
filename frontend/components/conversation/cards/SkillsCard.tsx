import { SkillsSection } from "@/components/profile/SkillsSection";
import type { Dictionary } from "@/lib/i18n/config";
import type { Profile } from "@/services/types";

import { CardFooterLink } from "./CardFooterLink";

export function SkillsCard({ profile, t }: { profile: Profile; t: Dictionary }) {
  return (
    <>
      <SkillsSection skills={profile.skills} />
      <CardFooterLink href="/about#skills" label={t.cards.aboutLink} />
    </>
  );
}
