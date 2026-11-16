import { EnglishContent } from "@/components/ui/EnglishContent";
import { Markdown } from "@/components/ui/Markdown";
import { SectionHeading } from "@/components/ui/SectionHeading";
import type { Dictionary } from "@/lib/i18n/config";
import type { Profile } from "@/services/types";

import { Timeline } from "./Timeline";

export function AboutSection({ profile, t }: { profile: Profile; t: Dictionary }) {
  const facts = [
    { label: t.profile.location, value: profile.location },
    { label: t.profile.languages, value: profile.languages.join(" · ") || null },
  ].filter((fact): fact is { label: string; value: string } => Boolean(fact.value));

  return (
    <>
      <div className="grid gap-12 lg:grid-cols-[1.4fr_1fr]">
        <EnglishContent>
          <Markdown className="text-base sm:text-lg">{profile.summary_markdown}</Markdown>
        </EnglishContent>

        <div className="space-y-8">
          {facts.length > 0 && (
            <dl className="divide-y divide-ink-800 rounded-2xl border border-ink-700 bg-ink-900">
              {facts.map((fact) => (
                <div key={fact.label} className="flex flex-col gap-1 px-5 py-4">
                  <dt className="font-mono text-xs uppercase tracking-[0.18em] text-mist-400">{fact.label}</dt>
                  <EnglishContent as="dd" className="text-mist-50">
                    {fact.value}
                  </EnglishContent>
                </div>
              ))}
            </dl>
          )}
          {profile.ways_of_working && (
            <div>
              <h3 className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-mist-400">
                {t.profile.waysOfWorking}
              </h3>
              <EnglishContent as="p" className="text-sm leading-relaxed text-mist-200">
                {profile.ways_of_working}
              </EnglishContent>
            </div>
          )}
        </div>
      </div>

      <div className="mt-20 grid gap-16 lg:grid-cols-2">
        {profile.experience && (
          <section aria-labelledby="experience">
            <SectionHeading id="experience" index="02" title={t.sections.experience} />
            <Timeline title={profile.experience.title} items={profile.experience.sections} />
          </section>
        )}
        {profile.education.length > 0 && (
          <section aria-labelledby="education">
            <SectionHeading id="education" index="03" title={t.sections.education} />
            <Timeline items={profile.education} />
          </section>
        )}
      </div>

      {profile.career_direction.length > 0 && (
        <section aria-labelledby="direction" className="mt-20">
          <SectionHeading id="direction" index="04" title={t.sections.direction} />
          <EnglishContent className="grid gap-6 sm:grid-cols-2">
            {profile.career_direction.map((item) => (
              <div key={item.heading} className="rounded-2xl border border-ink-700 bg-ink-900 p-6">
                <h3 className="font-mono text-xs uppercase tracking-[0.18em] text-accent">{item.heading}</h3>
                <Markdown className="mt-3 text-sm">{item.body_markdown}</Markdown>
              </div>
            ))}
          </EnglishContent>
        </section>
      )}
    </>
  );
}
