import type { ProjectSummary, UiAction } from "@/services/types";

// `/?card=<name>` values that may open a card; anything else is ignored.
const CARD_PARAMS: Record<string, UiAction> = {
  projects: { type: "show_projects" },
  skills: { type: "show_skills" },
  experience: { type: "show_experience" },
  education: { type: "show_education" },
  contact: { type: "show_contact" },
};

export type DeepLink =
  | { kind: "ask"; project: ProjectSummary } // `/?ask=<project_id>`: open the card and ask about it
  | { kind: "card"; card: UiAction }; // `/?card=<name>`: open the card only

/** Validate `?ask=<project_id>` / `?card=<name>` against known ids before acting on them. */
export function deepLinkFromParams(params: URLSearchParams, projects: ProjectSummary[] | null): DeepLink | null {
  const ask = params.get("ask");
  const project = ask ? projects?.find((p) => p.id === ask) : undefined;
  if (project) return { kind: "ask", project };
  const card = params.get("card");
  if (card && Object.hasOwn(CARD_PARAMS, card)) return { kind: "card", card: CARD_PARAMS[card] };
  return null;
}
