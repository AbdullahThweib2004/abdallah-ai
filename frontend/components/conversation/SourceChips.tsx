import Link from "next/link";

import type { ChatSource } from "@/services/types";

// Non-project sources link to their section on /about.
const ABOUT_ANCHORS: Record<string, string> = {
  about: "#about",
  experience: "#experience",
  education: "#education",
  skills: "#skills",
  interests: "#interests",
  goals: "#direction",
  "public-links": "#contact",
};

function hrefFor(source: ChatSource): string {
  return source.project_id ? `/projects/${source.project_id}` : `/about${ABOUT_ANCHORS[source.doc_id] ?? ""}`;
}

/** "Title › heading" chips for the knowledge an answer was grounded on. */
export function SourceChips({ sources, label }: { sources: ChatSource[]; label: string }) {
  if (sources.length === 0) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center justify-center gap-1.5">
      <span className="eyebrow me-1 text-mist-400">{label}</span>
      <ul aria-label={label} className="contents">
        {sources.map((source) => (
          <li key={`${source.doc_id}-${source.heading}`}>
            <Link
              href={hrefFor(source)}
              lang="en"
              dir="ltr"
              title={`${source.title} › ${source.heading}`}
              className="inline-block max-w-[16rem] truncate rounded-full border border-ink-700 bg-ink-900 px-2.5 py-0.5 align-middle text-xs text-mist-200 transition-colors hover:border-accent/60 hover:text-mist-50"
            >
              {source.title} <span aria-hidden="true">›</span>
              <span className="sr-only">,</span> {source.heading}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
