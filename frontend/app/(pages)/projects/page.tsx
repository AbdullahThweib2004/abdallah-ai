import { Suspense } from "react";

import { PageSkeleton } from "@/components/ui/Skeletons";
import type { Metadata } from "next";

import { ProjectCard } from "@/components/projects/ProjectCard";
import { ContentUnavailable } from "@/components/ui/ContentUnavailable";
import { PageHeader } from "@/components/ui/PageHeader";
import { TalkCta } from "@/components/ui/TalkCta";
import { getDictionary } from "@/lib/i18n/config";
import { getLocale } from "@/lib/i18n/server";
import { getProjects } from "@/services/content";

export async function generateMetadata(): Promise<Metadata> {
  return { title: getDictionary(await getLocale()).pages.projectsTitle };
}

async function ProjectsContent() {
  const [locale, projects] = await Promise.all([getLocale(), getProjects()]);
  const t = getDictionary(locale);

  return (
    <>
      <PageHeader
        title={t.pages.projectsTitle}
        intro={t.pages.projectsIntro}
        action={<TalkCta label={t.pages.talkCta} />}
      />
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
        {projects ? (
          // The API already orders projects: featured first, then by `order`.
          <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((project) => (
              <li key={project.id} className="flex">
                <ProjectCard project={project} t={t} />
              </li>
            ))}
          </ul>
        ) : (
          <ContentUnavailable t={t} />
        )}
      </div>
    </>
  );
}


// Request-time data (locale cookie, backend content) streams inside Suspense; the fallback is
// the static shell, so navigations stay instant under cacheComponents.
export default function ProjectsPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <ProjectsContent />
    </Suspense>
  );
}
