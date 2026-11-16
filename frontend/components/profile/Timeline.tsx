import { EnglishContent } from "@/components/ui/EnglishContent";
import { Markdown } from "@/components/ui/Markdown";
import type { ContentSection } from "@/services/types";

/** Vertical timeline; uses logical properties so the rail flips sides in RTL. */
export function Timeline({ title, items }: { title?: string; items: ContentSection[] }) {
  // Keep heading levels sequential: items sit one level below the optional title.
  const ItemHeading = title ? "h4" : "h3";
  return (
    <EnglishContent>
      {title && <h3 className="mb-6 text-lg font-semibold text-mist-50">{title}</h3>}
      <ol className="relative space-y-8 border-s border-ink-700 ps-6">
        {items.map((item) => (
          <li key={item.heading} className="relative">
            <span
              aria-hidden="true"
              className="absolute -start-[29px] top-1.5 size-2.5 rounded-full border-2 border-ink-950 bg-accent"
            />
            <ItemHeading className="font-mono text-xs uppercase tracking-[0.18em] text-accent">
              {item.heading}
            </ItemHeading>
            <Markdown className="mt-2 text-sm sm:text-base">{item.body_markdown}</Markdown>
          </li>
        ))}
      </ol>
    </EnglishContent>
  );
}
