import type { Dictionary } from "@/lib/i18n/config";

const WAVE_BARS = [0.45, 0.8, 0.6, 1, 0.7, 0.9, 0.5, 0.75, 0.4];

/** Static stand-in for the future avatar + conversation panel (build steps 4–9). */
export function ConversationPlaceholder({ t }: { t: Dictionary }) {
  return (
    <section
      aria-labelledby="conversation-title"
      className="relative overflow-hidden rounded-3xl border border-ink-700 bg-ink-900/80 p-6 shadow-[0_30px_80px_-40px_rgba(240,179,91,0.35)] sm:p-8"
    >
      <div className="flex items-center justify-between gap-4">
        <h2 id="conversation-title" className="font-mono text-xs uppercase tracking-[0.2em] text-mist-400">
          {t.conversation.title}
        </h2>
        <span className="whitespace-nowrap rounded-full border border-accent/40 px-2.5 py-0.5 text-xs font-medium text-accent">
          {t.conversation.comingSoon}
        </span>
      </div>

      <div aria-hidden="true" className="relative mx-auto my-10 grid size-40 place-items-center sm:size-48">
        <div className="orb-pulse absolute inset-0 rounded-full bg-[radial-gradient(circle_at_35%_30%,var(--color-accent-strong),var(--color-accent)_35%,transparent_70%)] opacity-90 blur-[2px]" />
        <div className="absolute inset-3 rounded-full border border-accent/30" />
        <div className="absolute -inset-4 rounded-full border border-ink-700" />
        <div className="relative flex h-10 items-center gap-1">
          {WAVE_BARS.map((height, index) => (
            <span
              key={index}
              className="wave-bar block w-1 origin-center rounded-full bg-accent-ink/80"
              style={{ height: `${height * 100}%`, ["--wave-delay" as string]: `${index * 110}ms` }}
            />
          ))}
        </div>
      </div>

      <p className="text-center text-sm leading-relaxed text-mist-200">{t.conversation.description}</p>

      <button
        type="button"
        disabled
        className="mt-6 w-full cursor-not-allowed rounded-full border border-ink-600 bg-ink-800 px-5 py-3 text-sm font-medium text-mist-200"
      >
        {t.conversation.button}
      </button>

      <p className="mt-4 text-center text-xs text-mist-400">{t.conversation.transparency}</p>
    </section>
  );
}
