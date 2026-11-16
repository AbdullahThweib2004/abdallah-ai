import type { ReactNode, Ref } from "react";

type Props = {
  title: string;
  closeLabel: string;
  onClose: () => void;
  headingRef: Ref<HTMLHeadingElement>;
  children: ReactNode;
};

/**
 * Desktop: a panel on the end side of the stage. Mobile: a bottom sheet over the lower half.
 * Its content scrolls internally so the page itself never scrolls.
 */
export function CardPanel({ title, closeLabel, onClose, headingRef, children }: Props) {
  return (
    <aside
      aria-labelledby="card-title"
      className="card-panel fixed inset-x-0 bottom-0 z-30 flex h-[58dvh] flex-col rounded-t-3xl border-t border-ink-700 bg-ink-900/95 shadow-[0_-30px_80px_-30px_rgba(0,0,0,0.9)] backdrop-blur-md lg:absolute lg:inset-x-auto lg:inset-y-4 lg:end-4 lg:h-auto lg:w-[var(--panel-width)] lg:rounded-3xl lg:border"
    >
      <div aria-hidden="true" className="mx-auto mt-2.5 h-1 w-10 rounded-full bg-ink-600 lg:hidden" />
      <header className="flex items-center justify-between gap-4 border-b border-ink-800 px-5 py-3.5 sm:px-6">
        <h2
          id="card-title"
          ref={headingRef}
          tabIndex={-1}
          className="font-mono text-xs uppercase tracking-[0.2em] text-mist-400 focus-visible:outline-none"
        >
          {title}
        </h2>
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
        {children}
      </div>
    </aside>
  );
}
