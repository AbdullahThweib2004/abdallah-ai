import { EnglishContent } from "@/components/ui/EnglishContent";
import type { Profile } from "@/services/types";

export function InterestsSection({ interests }: { interests: Profile["interests"] }) {
  return (
    <EnglishContent className="@container">
      {interests.summary && (
        <p className="max-w-3xl text-base leading-relaxed text-mist-200 sm:text-lg">{interests.summary}</p>
      )}
      <ul className="mt-8 grid gap-3 @xl:grid-cols-2 @4xl:grid-cols-3">
        {interests.items.map((item) => (
          <li
            key={item}
            className="flex items-start gap-3 rounded-xl border border-ink-700 bg-ink-900 px-4 py-3 text-sm text-mist-50"
          >
            <span aria-hidden="true" className="mt-1.5 size-1.5 shrink-0 rounded-full bg-accent" />
            {item}
          </li>
        ))}
      </ul>
    </EnglishContent>
  );
}
