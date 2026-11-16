import Link from "next/link";

import { TechChips } from "@/components/projects/TechChips";
import { EnglishContent } from "@/components/ui/EnglishContent";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Dictionary } from "@/lib/i18n/config";
import type { ProjectSummary } from "@/services/types";

export function ProjectCard({ project, t }: { project: ProjectSummary; t: Dictionary }) {
  return (
    <article className="space-y-5">
      <StatusBadge status={project.project_status} t={t} />
      <EnglishContent>
        <h3 className="text-2xl font-semibold leading-tight tracking-tight text-mist-50">{project.title}</h3>
        {project.one_line_summary && (
          <p className="mt-3 leading-relaxed text-mist-200">{project.one_line_summary}</p>
        )}
      </EnglishContent>
      {project.technologies.length > 0 && (
        <div>
          <h4 className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-mist-400">{t.projects.technologies}</h4>
          <TechChips items={project.technologies} limit={6} moreLabel={t.projects.moreTech} />
        </div>
      )}
      <div className="flex flex-wrap gap-3 pt-1">
        <Link
          href={`/projects/${project.id}`}
          className="inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-strong"
        >
          {t.cards.openProject}
          <span aria-hidden="true" className="rtl:rotate-180">
            →
          </span>
        </Link>
        {project.repository_url && (
          <a
            href={project.repository_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-full border border-ink-600 px-5 py-2.5 text-sm font-medium text-mist-50 transition-colors hover:border-accent/60"
          >
            {t.projects.repository}
            <span className="sr-only"> ({t.contact.opensInNewTab})</span>
            <span aria-hidden="true">↗</span>
          </a>
        )}
      </div>
    </article>
  );
}
