import { ContentUnavailable } from "@/components/ui/ContentUnavailable";
import type { Dictionary } from "@/lib/i18n/config";
import type { ContactResponse, Profile, ProjectSummary, UiAction } from "@/services/types";

import { ContactCard } from "./cards/ContactCard";
import { EducationCard } from "./cards/EducationCard";
import { ExperienceCard } from "./cards/ExperienceCard";
import { ProjectCard } from "./cards/ProjectCard";
import { ProjectsCard } from "./cards/ProjectsCard";
import { SkillsCard } from "./cards/SkillsCard";

export type CardData = {
  profile: Profile | null;
  projects: ProjectSummary[] | null;
  contact: ContactResponse | null;
};

/** Renders the card for an action; every value comes from the API data passed in. */
export function CardBody({ card, data, t }: { card: UiAction; data: CardData; t: Dictionary }) {
  const { profile, projects, contact } = data;
  const unavailable = <ContentUnavailable t={t} />;

  switch (card.type) {
    case "show_project": {
      const project = projects?.find((p) => p.id === card.project_id);
      return project ? <ProjectCard project={project} t={t} /> : unavailable;
    }
    case "show_projects":
      return projects ? <ProjectsCard projects={projects} t={t} /> : unavailable;
    case "show_skills":
      return profile ? <SkillsCard profile={profile} t={t} /> : unavailable;
    case "show_experience":
      return profile ? <ExperienceCard profile={profile} t={t} /> : unavailable;
    case "show_education":
      return profile ? <EducationCard profile={profile} t={t} /> : unavailable;
    case "show_contact":
      return contact ? <ContactCard contact={contact} t={t} /> : unavailable;
  }
}
