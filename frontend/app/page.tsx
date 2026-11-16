import { ContactSection } from "@/components/profile/ContactSection";
import { AboutSection } from "@/components/profile/AboutSection";
import { Hero } from "@/components/profile/Hero";
import { InterestsSection } from "@/components/profile/InterestsSection";
import { SkillsSection } from "@/components/profile/SkillsSection";
import { ProjectCard } from "@/components/projects/ProjectCard";
import { ProjectList } from "@/components/projects/ProjectList";
import { ContentUnavailable } from "@/components/ui/ContentUnavailable";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { getDictionary } from "@/lib/i18n/config";
import { getLocale } from "@/lib/i18n/server";
import { getContact, getProfile, getProjects } from "@/services/content";

const SECTION = "mx-auto max-w-6xl scroll-mt-20 px-4 py-16 sm:px-6 sm:py-20 lg:px-8";

export default async function Home() {
  const [locale, profile, projects, contact] = await Promise.all([
    getLocale(),
    getProfile(),
    getProjects(),
    getContact(),
  ]);
  const t = getDictionary(locale);
  const featured = projects?.filter((project) => project.featured) ?? [];

  return (
    <>
      <Hero profile={profile} t={t} locale={locale} />

      <section id="projects" aria-labelledby="projects-title" className={SECTION}>
        <SectionHeading id="projects-title" index="01" title={t.sections.featured} />
        {projects ? (
          <>
            <div className="grid gap-5 sm:grid-cols-2">
              {featured.map((project) => (
                <ProjectCard key={project.id} project={project} t={t} />
              ))}
            </div>
            <h3 className="mb-5 mt-16 text-lg font-semibold text-mist-50">{t.sections.allProjects}</h3>
            <ProjectList projects={projects} t={t} />
          </>
        ) : (
          <ContentUnavailable t={t} />
        )}
      </section>

      <section id="about" aria-labelledby="about-title" className={SECTION}>
        <SectionHeading id="about-title" index="02" title={t.sections.about} />
        {profile ? <AboutSection profile={profile} t={t} /> : <ContentUnavailable t={t} />}
      </section>

      {profile && profile.skills.length > 0 && (
        <section id="skills" aria-labelledby="skills-title" className={SECTION}>
          <SectionHeading id="skills-title" index="06" title={t.sections.skills} />
          <SkillsSection skills={profile.skills} />
        </section>
      )}

      {profile && profile.interests.items.length > 0 && (
        <section id="interests" aria-labelledby="interests-title" className={SECTION}>
          <SectionHeading id="interests-title" index="07" title={t.sections.interests} />
          <InterestsSection interests={profile.interests} />
        </section>
      )}

      <section id="contact" aria-labelledby="contact-title" className={SECTION}>
        <SectionHeading id="contact-title" index="08" title={t.sections.contact} />
        {contact ? <ContactSection links={contact.links} t={t} /> : <ContentUnavailable t={t} />}
      </section>
    </>
  );
}
