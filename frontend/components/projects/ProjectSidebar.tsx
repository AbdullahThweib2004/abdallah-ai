import { EnglishContent } from "@/components/ui/EnglishContent";
import { Markdown } from "@/components/ui/Markdown";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Dictionary, Locale } from "@/lib/i18n/config";
import type { ProjectDetail } from "@/services/types";

import { TechChips } from "./TechChips";

type Props = { project: ProjectDetail; statusNote: string | null; t: Dictionary; locale: Locale };

export function ProjectSidebar({ project, statusNote, t, locale }: Props) {
  const links = [
    { href: project.repository_url, label: t.projects.repository, primary: true },
    { href: project.demo_url, label: t.projects.demo, primary: false },
  ].filter((link): link is { href: string; label: string; primary: boolean } => Boolean(link.href));

  return (
    <aside className="space-y-8 rounded-2xl border border-ink-700 bg-ink-900 p-6 lg:sticky lg:top-24">
      <div>
        <h2 className="mb-3 font-mono text-xs uppercase tracking-[0.2em] text-mist-400">{t.projects.status}</h2>
        <StatusBadge status={project.project_status} t={t} />
        {statusNote && (
          <EnglishContent className="mt-3 text-sm">
            <Markdown>{statusNote}</Markdown>
          </EnglishContent>
        )}
      </div>

      {project.technologies.length > 0 && (
        <div>
          <h2 className="mb-3 font-mono text-xs uppercase tracking-[0.2em] text-mist-400">
            {t.projects.technologies}
          </h2>
          <TechChips items={project.technologies} />
        </div>
      )}

      {links.length > 0 && (
        <div className="flex flex-col gap-3">
          {links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              target="_blank"
              rel="noopener noreferrer"
              className={`inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium transition-colors ${
                link.primary
                  ? "bg-accent text-accent-ink hover:bg-accent-strong"
                  : "border border-ink-600 text-mist-50 hover:border-accent/60"
              }`}
            >
              {link.label}
              <span className="sr-only"> ({t.contact.opensInNewTab})</span>
              <span aria-hidden="true">↗</span>
            </a>
          ))}
        </div>
      )}

      {project.last_reviewed && (
        <p className="text-xs text-mist-400">
          {t.projects.lastReviewed}:{" "}
          <time dateTime={project.last_reviewed}>
            {new Date(`${project.last_reviewed}T00:00:00Z`).toLocaleDateString(locale === "ar" ? "ar" : "en", {
              year: "numeric",
              month: "long",
              day: "numeric",
              timeZone: "UTC",
            })}
          </time>
        </p>
      )}
    </aside>
  );
}
