import Link from "next/link";

import { EnglishContent } from "@/components/ui/EnglishContent";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Dictionary } from "@/lib/i18n/config";
import type { ProjectSummary } from "@/services/types";

/** Compact, scannable list of every project. */
export function ProjectList({ projects, t }: { projects: ProjectSummary[]; t: Dictionary }) {
  return (
    <ul className="divide-y divide-ink-800 overflow-hidden rounded-2xl border border-ink-700">
      {projects.map((project) => (
        <li key={project.id}>
          <Link
            href={`/projects/${project.id}`}
            className="group flex flex-col gap-2 bg-ink-900/40 px-5 py-4 transition-colors hover:bg-ink-850 sm:flex-row sm:items-center sm:gap-6"
          >
            <EnglishContent className="min-w-0 flex-1 text-start">
              <span className="block font-medium text-mist-50">{project.title}</span>
              {project.one_line_summary && (
                <span className="mt-1 block truncate text-sm text-mist-400">{project.one_line_summary}</span>
              )}
            </EnglishContent>
            <span className="flex shrink-0 items-center gap-3">
              <StatusBadge status={project.project_status} t={t} />
              <span aria-hidden="true" className="text-mist-400 transition-colors group-hover:text-accent rtl:rotate-180">
                →
              </span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
