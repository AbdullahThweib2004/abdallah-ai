"use client";

import { useEffect, useRef, useState } from "react";

type Props = { label: string; suggestions: string[]; onPick: (text: string) => void };

/** Distance from each edge (in px) before a fade is shown. */
const EDGE_TOLERANCE = 4;

/**
 * Mobile: one horizontally scrolling row with a fade on each side that still has hidden
 * chips (start/end, so it works in RTL too). From `sm` up the chips wrap and never scroll.
 */
export function SuggestionChips({ label, suggestions, onPick }: Props) {
  const listRef = useRef<HTMLUListElement>(null);
  const [edges, setEdges] = useState({ start: false, end: false });

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    function update() {
      if (!list) return;
      // scrollLeft is negative in RTL (Chromium/Firefox), so compare magnitudes.
      const position = Math.abs(list.scrollLeft);
      const max = list.scrollWidth - list.clientWidth;
      setEdges({ start: position > EDGE_TOLERANCE, end: position < max - EDGE_TOLERANCE });
    }
    const observer = new ResizeObserver(update);
    observer.observe(list);
    list.addEventListener("scroll", update, { passive: true });
    return () => {
      observer.disconnect();
      list.removeEventListener("scroll", update);
    };
  }, []);

  const fade = "pointer-events-none absolute inset-y-0 w-12 from-ink-950 to-transparent transition-opacity sm:hidden";

  return (
    <div className="relative -mx-4 sm:mx-0" data-greeting-skip>
      <ul
        ref={listRef}
        aria-label={label}
        className="flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none] sm:flex-wrap sm:justify-center sm:overflow-visible sm:px-0"
      >
        {suggestions.map((suggestion) => (
          <li key={suggestion} className="shrink-0">
            <button
              type="button"
              onClick={() => onPick(suggestion)}
              className="whitespace-nowrap rounded-full border border-ink-700 bg-ink-900/80 px-3.5 py-1.5 text-sm text-mist-200 transition-colors hover:border-accent/60 hover:text-mist-50"
            >
              {suggestion}
            </button>
          </li>
        ))}
      </ul>
      <span
        aria-hidden="true"
        className={`${fade} start-0 bg-linear-to-r rtl:bg-linear-to-l ${edges.start ? "opacity-100" : "opacity-0"}`}
      />
      <span
        aria-hidden="true"
        className={`${fade} end-0 bg-linear-to-l rtl:bg-linear-to-r ${edges.end ? "opacity-100" : "opacity-0"}`}
      />
    </div>
  );
}
