import Link from "next/link";

import { EnglishContent } from "@/components/ui/EnglishContent";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Dictionary } from "@/lib/i18n/config";
import type { ProjectSummary } from "@/services/types";

import { TechChips } from "./TechChips";

export function ProjectCard({ project, t }: { project: ProjectSummary; t: Dictionary }) {
  const titleId = `project-${project.id}`;

  return (
    <article
      aria-labelledby={titleId}
      className="group relative flex w-full flex-col rounded-2xl border border-ink-700 bg-ink-900 p-6 transition-colors hover:border-accent/50 focus-within:border-accent/50"
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <StatusBadge status={project.project_status} t={t} />
      </div>
      <EnglishContent>
        <h3 id={titleId} className="text-lg font-semibold leading-snug text-mist-50">
          {project.title}
        </h3>
        {project.one_line_summary && (
          <p className="mt-3 line-clamp-4 text-sm leading-relaxed text-mist-200">{project.one_line_summary}</p>
        )}
      </EnglishContent>
      <div className="mt-5">
        <TechChips items={project.technologies} limit={4} moreLabel={t.projects.moreTech} />
      </div>
      <Link
        href={`/projects/${project.id}`}
        className="mt-6 inline-flex items-center gap-2 self-start text-sm font-medium text-accent after:absolute after:inset-0 after:rounded-2xl hover:text-accent-strong"
      >
        {t.projects.viewDetails}
        <span className="sr-only">
          : <span lang="en">{project.title}</span>
        </span>
        <span aria-hidden="true" className="transition-transform group-hover:translate-x-0.5 rtl:rotate-180 rtl:group-hover:-translate-x-0.5">
          →
        </span>
      </Link>
    </article>
  );
}
