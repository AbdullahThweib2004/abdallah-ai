import type { AssistantKind } from "@/hooks/useConversation";
import type { ProjectSummary, UiAction } from "@/services/types";

// `/?card=<name>` values that may open a card; anything else is ignored.
const CARD_PARAMS: Record<string, UiAction> = {
  projects: { type: "show_projects" },
  skills: { type: "show_skills" },
  experience: { type: "show_experience" },
  education: { type: "show_education" },
  contact: { type: "show_contact" },
};

/** Validate `?ask=<project_id>` / `?card=<name>` against known ids before opening anything. */
export function actionFromParams(
  params: URLSearchParams,
  projects: ProjectSummary[] | null,
): { card: UiAction; kind?: AssistantKind } | null {
  const ask = params.get("ask");
  if (ask && projects?.some((project) => project.id === ask)) {
    return { card: { type: "show_project", project_id: ask }, kind: "askProject" };
  }
  const card = params.get("card");
  if (card && Object.hasOwn(CARD_PARAMS, card)) return { card: CARD_PARAMS[card] };
  return null;
}
