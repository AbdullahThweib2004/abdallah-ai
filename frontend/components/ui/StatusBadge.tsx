import type { Dictionary } from "@/lib/i18n/config";
import type { ProjectStatus } from "@/services/types";

const STYLES: Record<ProjectStatus, string> = {
  completed: "border-ok/40 text-ok",
  in_progress: "border-warn/40 text-warn",
  research: "border-info/40 text-info",
};

export function StatusBadge({ status, t }: { status: ProjectStatus | null; t: Dictionary }) {
  if (status === null) return null;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${STYLES[status]}`}
    >
      <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
      {t.projects.statusLabels[status]}
    </span>
  );
}
