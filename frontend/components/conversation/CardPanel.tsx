import type { ReactNode, Ref } from "react";

type Props = {
  /** Small decorative label (hidden from assistive tech; the heading carries the meaning). */
  eyebrow: string;
  /** The card's real heading: the project title or the card's section title. */
  heading: string;
  /** Set to "en" when the heading is knowledge-base content (e.g. a project title). */
  headingLang?: "en";
  closeLabel: string;
  onClose: () => void;
  headingRef: Ref<HTMLHeadingElement>;
  /** The other card the AI requested with this answer (e.g. two compared projects). */
  alternative?: { label: string; lang?: "en"; switchLabel: string; onSelect: () => void };
  children: ReactNode;
};

/**
 * Desktop: a panel on the end side of the stage. Mobile: a bottom sheet over the lower half.
 * Its content scrolls internally so the page itself never scrolls. Focus is moved to the
 * heading when the card opens.
 */
export function CardPanel({
  eyebrow,
  heading,
  headingLang,
  closeLabel,
  onClose,
  headingRef,
  alternative,
  children,
}: Props) {
  return (
    <aside
      aria-labelledby="card-heading"
      className="card-panel fixed inset-x-0 bottom-0 z-30 flex h-[58dvh] flex-col rounded-t-3xl border-t border-ink-700 bg-ink-900/95 shadow-[0_-30px_80px_-30px_rgba(0,0,0,0.9)] backdrop-blur-md lg:absolute lg:inset-x-auto lg:inset-y-4 lg:end-4 lg:h-auto lg:w-[var(--panel-width)] lg:rounded-3xl lg:border"
    >
      <div aria-hidden="true" className="mx-auto mt-2.5 h-1 w-10 rounded-full bg-ink-600 lg:hidden" />
      <header className="flex items-center justify-between gap-4 border-b border-ink-800 px-5 py-3 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <p aria-hidden="true" className="eyebrow shrink-0 text-mist-400">
            {eyebrow}
          </p>
          {alternative && (
            <button
              type="button"
              onClick={alternative.onSelect}
              aria-label={`${alternative.switchLabel}: ${alternative.label}`}
              className="flex min-w-0 items-center gap-1.5 rounded-full border border-ink-700 py-1 pe-3 ps-1 text-xs text-mist-200 transition-colors hover:border-accent/60 hover:text-mist-50"
            >
              <span aria-hidden="true" className="grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1 font-semibold text-accent-ink">
                +1
              </span>
              <span lang={alternative.lang} className="truncate">
                {alternative.label}
              </span>
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label={closeLabel}
          className="grid size-9 place-items-center rounded-full text-mist-200 transition-colors hover:bg-ink-800 hover:text-mist-50"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 6l12 12M18 6 6 18" strokeLinecap="round" />
          </svg>
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:px-6">
        <h2
          id="card-heading"
          ref={headingRef}
          tabIndex={-1}
          lang={headingLang}
          dir={headingLang ? "ltr" : undefined}
          className="mb-5 text-2xl font-semibold leading-tight tracking-tight text-mist-50"
        >
          {heading}
        </h2>
        {children}
      </div>
    </aside>
  );
}
