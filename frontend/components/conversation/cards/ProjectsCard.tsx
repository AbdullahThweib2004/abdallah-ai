import { ProjectList } from "@/components/projects/ProjectList";
import type { Dictionary } from "@/lib/i18n/config";
import type { ProjectSummary } from "@/services/types";

import { CardFooterLink } from "./CardFooterLink";

export function ProjectsCard({ projects, t }: { projects: ProjectSummary[]; t: Dictionary }) {
  return (
    <>
      <ProjectList projects={projects} t={t} />
      <CardFooterLink href="/projects" label={t.cards.allProjectsLink} />
    </>
  );
}
