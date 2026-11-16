import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ProjectSidebar } from "@/components/projects/ProjectSidebar";
import { ContentUnavailable } from "@/components/ui/ContentUnavailable";
import { EnglishContent } from "@/components/ui/EnglishContent";
import { Markdown } from "@/components/ui/Markdown";
import { getDictionary } from "@/lib/i18n/config";
import { getLocale } from "@/lib/i18n/server";
import { getProject } from "@/services/content";

// Shown in the page header / sidebar instead of the section list.
const HEADER_SECTIONS = new Set(["One-line summary", "Status"]);

export async function generateMetadata({ params }: PageProps<"/projects/[id]">): Promise<Metadata> {
  const { id } = await params;
  const result = await getProject(id);
  if (result.status !== "ok") return {};
  const { project } = result;
  return {
    title: project.title,
    description: project.one_line_summary ?? undefined,
    openGraph: { title: project.title, description: project.one_line_summary ?? undefined },
  };
}

export default async function ProjectPage({ params }: PageProps<"/projects/[id]">) {
  const [{ id }, locale] = await Promise.all([params, getLocale()]);
  const t = getDictionary(locale);
  const result = await getProject(id);

  if (result.status === "not_found") notFound();

  const backLink = (
    <Link
      href="/projects"
      className="inline-flex items-center gap-2 text-sm text-mist-400 transition-colors hover:text-mist-50"
    >
      <span aria-hidden="true" className="rtl:rotate-180">
        ←
      </span>
      {t.projects.backToProjects}
    </Link>
  );

  if (result.status === "unavailable") {
    return (
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:px-8">
        {backLink}
        <div className="mt-10">
          <ContentUnavailable t={t} />
        </div>
      </div>
    );
  }

  const { project } = result;
  const statusNote = project.sections.find((section) => section.heading === "Status")?.body_markdown ?? null;
  const sections = project.sections.filter((section) => !HEADER_SECTIONS.has(section.heading));

  return (
    <article className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
      {backLink}

      <header className="lab-backdrop -mx-4 mt-8 rounded-3xl px-4 py-10 sm:mx-0 sm:border sm:border-ink-800 sm:px-10">
        <EnglishContent>
          <p className="font-mono text-xs uppercase tracking-[0.25em] text-accent">{project.id}</p>
          <h1 className="mt-4 max-w-4xl text-4xl font-semibold leading-tight tracking-tight text-mist-50 sm:text-5xl">
            {project.title}
          </h1>
          {project.one_line_summary && (
            <p className="mt-5 max-w-3xl text-lg leading-relaxed text-mist-200">{project.one_line_summary}</p>
          )}
        </EnglishContent>
        <Link
          href={`/?ask=${project.id}`}
          className="mt-8 inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-strong"
        >
          {t.pages.askAboutProject}
          <span aria-hidden="true" className="rtl:rotate-180">
            →
          </span>
        </Link>
      </header>

      <div className="mt-12 grid gap-12 lg:grid-cols-[1fr_320px]">
        <EnglishContent className="min-w-0 space-y-12">
          {sections.map((section) => (
            <section key={section.heading} aria-labelledby={slug(section.heading)}>
              <h2 id={slug(section.heading)} className="mb-4 text-xl font-semibold text-mist-50">
                {section.heading}
              </h2>
              <Markdown>{section.body_markdown}</Markdown>
            </section>
          ))}
        </EnglishContent>
        <div className="lg:order-none">
          <ProjectSidebar project={project} statusNote={statusNote} t={t} locale={locale} />
        </div>
      </div>
    </article>
  );
}

function slug(text: string): string {
  return `section-${text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;
}
