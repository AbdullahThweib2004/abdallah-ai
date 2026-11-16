import { Chip } from "@/components/ui/Chip";
import { EnglishContent } from "@/components/ui/EnglishContent";
import type { Profile } from "@/services/types";

// Groups whose items are full sentences read better as a list than as chips.
const CHIP_MAX_LENGTH = 70;

export function SkillsSection({ skills }: { skills: Profile["skills"] }) {
  return (
    <EnglishContent className="grid gap-5 md:grid-flow-dense md:grid-cols-2">
      {skills.map((group) => {
        const asChips = group.items.every((item) => item.length <= CHIP_MAX_LENGTH);
        return (
          <div
            key={group.category}
            className={`rounded-2xl border border-ink-700 bg-ink-900 p-6 ${asChips ? "" : "md:col-span-2"}`}
          >
            <h3 className="mb-4 text-sm font-semibold text-mist-50">{group.category}</h3>
            {asChips ? (
              <ul className="flex flex-wrap gap-2">
                {group.items.map((item) => (
                  <li key={item}>
                    <Chip>{item}</Chip>
                  </li>
                ))}
              </ul>
            ) : (
              <ul className="prose-lab list-disc space-y-2 ps-5 text-sm">
                {group.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </EnglishContent>
  );
}
