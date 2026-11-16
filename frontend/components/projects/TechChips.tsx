import { Chip } from "@/components/ui/Chip";
import { EnglishContent } from "@/components/ui/EnglishContent";

export function TechChips({ items, limit, moreLabel }: { items: string[]; limit?: number; moreLabel?: string }) {
  const shown = limit ? items.slice(0, limit) : items;
  const hidden = items.length - shown.length;

  return (
    <ul className="flex flex-wrap gap-1.5">
      {shown.map((item) => (
        <li key={item}>
          <EnglishContent as="span">
            <Chip>{item}</Chip>
          </EnglishContent>
        </li>
      ))}
      {hidden > 0 && (
        <li>
          <Chip>
            +{hidden} {moreLabel}
          </Chip>
        </li>
      )}
    </ul>
  );
}
