// Mirrors the backend response models in backend/app/models/{content,health}.py.

export type ProjectStatus = "completed" | "in_progress" | "research";
export type LinkKind = "github" | "linkedin" | "email" | "demo" | "other";

export type HealthResponse = {
  status: "ok";
  version: string;
  knowledge_base: "ok" | "error";
  approved_documents: number;
};

export type ContentSection = {
  heading: string;
  body_markdown: string;
};

export type Profile = {
  name: string;
  name_ar: string | null;
  headline: string;
  summary_markdown: string;
  location: string | null;
  languages: string[];
  intro: { en: string | null; ar: string | null };
  ways_of_working: string | null;
  education: ContentSection[];
  experience: { title: string; sections: ContentSection[] } | null;
  skills: { category: string; items: string[] }[];
  interests: { summary: string | null; items: string[] };
  career_direction: ContentSection[];
};

export type ProjectSummary = {
  id: string;
  title: string;
  one_line_summary: string | null;
  project_status: ProjectStatus | null;
  technologies: string[];
  featured: boolean;
  repository_url: string | null;
  demo_url: string | null;
  tags: string[];
};

export type ProjectDetail = ProjectSummary & {
  last_reviewed: string | null;
  sections: ContentSection[];
};

export type ContactLink = {
  link_id: string;
  label: string;
  url: string;
  kind: LinkKind;
};

export type ContactResponse = {
  links: ContactLink[];
};

// UI actions the conversation can request (spec §11 allowlist). From step 6 the backend
// validates these against known ids; the frontend only ever renders them as cards.
export type UiAction =
  | { type: "show_project"; project_id: string }
  | { type: "show_projects" }
  | { type: "show_skills" }
  | { type: "show_experience" }
  | { type: "show_education" }
  | { type: "show_contact" };

export type CardType = UiAction["type"];

// --- Chat (POST /api/v1/chat, Server-Sent Events) -------------------------------------------

export type ChatLanguage = "en" | "ar";

export type ChatTurn = { role: "user" | "assistant"; content: string };

export type ChatRequest = { message: string; history: ChatTurn[]; ui_language: ChatLanguage };

export type ChatEvent =
  | { type: "start"; request_id: string; language: ChatLanguage }
  | { type: "token"; text: string }
  | { type: "done"; usage: { input_tokens: number; output_tokens: number }; latency_ms: number }
  | { type: "error"; code: "unavailable" | "timeout" | "busy"; message: string };
