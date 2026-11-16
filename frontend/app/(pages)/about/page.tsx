import type { Metadata } from "next";

import { AboutSection } from "@/components/profile/AboutSection";
import { ContactSection } from "@/components/profile/ContactSection";
import { InterestsSection } from "@/components/profile/InterestsSection";
import { SkillsSection } from "@/components/profile/SkillsSection";
import { ContentUnavailable } from "@/components/ui/ContentUnavailable";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { TalkCta } from "@/components/ui/TalkCta";
import { getDictionary } from "@/lib/i18n/config";
import { getLocale } from "@/lib/i18n/server";
import { getContact, getProfile } from "@/services/content";

const SECTION = "mx-auto max-w-6xl scroll-mt-20 px-4 py-14 sm:px-6 lg:px-8";

export async function generateMetadata(): Promise<Metadata> {
  return { title: getDictionary(await getLocale()).pages.aboutTitle };
}

export default async function AboutPage() {
  const [locale, profile, contact] = await Promise.all([getLocale(), getProfile(), getContact()]);
  const t = getDictionary(locale);

  return (
    <>
      <PageHeader title={t.pages.aboutTitle} action={<TalkCta label={t.pages.talkCta} />} />

      <section id="about" aria-labelledby="about-title" className={SECTION}>
        <SectionHeading id="about-title" index="01" title={t.sections.about} />
        {profile ? <AboutSection profile={profile} t={t} /> : <ContentUnavailable t={t} />}
      </section>

      {profile && profile.skills.length > 0 && (
        <section id="skills" aria-labelledby="skills-title" className={SECTION}>
          <SectionHeading id="skills-title" index="05" title={t.sections.skills} />
          <SkillsSection skills={profile.skills} />
        </section>
      )}

      {profile && profile.interests.items.length > 0 && (
        <section id="interests" aria-labelledby="interests-title" className={SECTION}>
          <SectionHeading id="interests-title" index="06" title={t.sections.interests} />
          <InterestsSection interests={profile.interests} />
        </section>
      )}

      <section id="contact" aria-labelledby="contact-title" className={SECTION}>
        <SectionHeading id="contact-title" index="07" title={t.sections.contact} />
        {contact ? <ContactSection links={contact.links} t={t} /> : <ContentUnavailable t={t} />}
        <div className="mt-12">
          <TalkCta label={t.pages.talkCta} />
        </div>
      </section>
    </>
  );
}
