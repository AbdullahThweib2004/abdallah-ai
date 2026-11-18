import { existsSync } from "node:fs";
import path from "node:path";
import { Suspense } from "react";

import { PageSkeleton } from "@/components/ui/Skeletons";
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

/** Optional authorized photo of Abdallah, shown next to the About text when the file exists. */
const PHOTO = "/avatar/abdallah.jpg";

const SECTION = "mx-auto max-w-6xl scroll-mt-20 px-4 py-14 sm:px-6 lg:px-8";

export async function generateMetadata(): Promise<Metadata> {
  return { title: getDictionary(await getLocale()).pages.aboutTitle };
}

async function AboutContent() {
  const [locale, profile, contact] = await Promise.all([getLocale(), getProfile(), getContact()]);
  const t = getDictionary(locale);
  const photoSrc = existsSync(path.join(process.cwd(), "public", PHOTO)) ? PHOTO : null;

  return (
    <>
      <PageHeader title={t.pages.aboutTitle} action={<TalkCta label={t.pages.talkCta} />} />

      <section id="about" aria-labelledby="about-title" className={SECTION}>
        <SectionHeading id="about-title" index="01" title={t.sections.about} />
        {profile ? <AboutSection profile={profile} t={t} photoSrc={photoSrc} /> : <ContentUnavailable t={t} />}
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


// Request-time data (locale cookie, backend content) streams inside Suspense; the fallback is
// the static shell, so navigations stay instant under cacheComponents.
export default function AboutPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <AboutContent />
    </Suspense>
  );
}
