import type { ReactNode } from "react";

export function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md border border-ink-700 bg-ink-850 px-2 py-0.5 font-mono text-xs text-mist-200">
      {children}
    </span>
  );
}
