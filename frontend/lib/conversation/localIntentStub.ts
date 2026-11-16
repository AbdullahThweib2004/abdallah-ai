// TEMPORARY: replaced by validated AI actions in step 6
//
// Maps visitor text to a UI action with plain keyword matching so the card panel can be
// used before the AI exists. It never produces an answer, only which card to show.

import type { ProjectSummary, UiAction } from "@/services/types";

type Category = Exclude<UiAction["type"], "show_project">;

// Checked in this order after a specific project match. Arabic keywords also match as part
// of a longer word (e.g. "مشاريعه" contains "مشاريع").
const KEYWORDS: [Category, string[]][] = [
  ["show_contact", ["contact", "email", "mail", "linkedin", "reach", "hire", "تواصل", "اتصال", "بريد", "ايميل", "لينكد"]],
  ["show_experience", ["experience", "bank", "training", "intern", "internship", "job", "work", "خبره", "تدريب", "بنك", "عمل", "وظيفه"]],
  ["show_education", ["education", "university", "degree", "study", "graduate", "erasmus", "تعليم", "جامعه", "شهاده", "دراسه", "تخرج"]],
  ["show_skills", ["skill", "skills", "rag", "mcp", "tech", "stack", "technologies", "languages", "مهارات", "مهاره", "تقنيات", "لغات"]],
  ["show_projects", ["project", "projects", "portfolio", "built", "مشاريع", "مشروع", "اعمال"]],
];

const CATEGORY_WORDS = new Set(KEYWORDS.flatMap(([, words]) => words));
const ARABIC = /[؀-ۿ]/;

/** Lowercase; strip Arabic diacritics/tatweel and unify letter variants (أإآ→ا, ة→ه, ى→ي). */
export function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/[ً-ٰٟـ]/g, "")
    .replace(/[أإآ]/g, "ا")
    .replace(/ة/g, "ه")
    .replace(/ى/g, "ي");
}

function tokenize(text: string): string[] {
  return normalize(text).split(/[^\p{L}\p{N}]+/u).filter(Boolean);
}

function matchesWord(tokens: string[], word: string): boolean {
  return tokens.some((token) => token === word || (ARABIC.test(word) && token.includes(word)));
}

/** Words that identify exactly one project (from its id, title and tags). */
function distinctiveTokens(projects: ProjectSummary[]): Map<string, Set<string>> {
  const perProject = new Map(
    projects.map((p) => [p.id, new Set(tokenize([p.id, p.title, ...p.tags].join(" ")))]),
  );
  const counts = new Map<string, number>();
  for (const words of perProject.values()) {
    for (const word of words) counts.set(word, (counts.get(word) ?? 0) + 1);
  }
  for (const words of perProject.values()) {
    for (const word of [...words]) {
      if (word.length < 3 || counts.get(word) !== 1 || CATEGORY_WORDS.has(word)) words.delete(word);
    }
  }
  return perProject;
}

export function matchIntent(text: string, projects: ProjectSummary[]): UiAction | null {
  const tokens = tokenize(text);
  if (tokens.length === 0) return null;

  for (const [projectId, words] of distinctiveTokens(projects)) {
    if (tokens.includes(projectId) || [...words].some((word) => tokens.includes(word))) {
      return { type: "show_project", project_id: projectId };
    }
  }
  for (const [type, words] of KEYWORDS) {
    if (words.some((word) => matchesWord(tokens, normalize(word)))) return { type };
  }
  return null;
}
