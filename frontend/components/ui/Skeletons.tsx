/**
 * Static fallbacks for the Suspense boundaries around request-time content (locale cookie,
 * backend data). They use no request data, so they are part of the prerendered shell.
 */

export function HomeSkeleton() {
  return (
    <div aria-hidden="true" className="grid h-[calc(100dvh-var(--header-height))] place-items-center">
      <div className="size-[min(60vw,320px)] animate-pulse rounded-full border border-accent/20 bg-ink-900 shadow-[0_0_70px_-12px_rgba(240,179,91,0.35)] motion-reduce:animate-none" />
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div aria-hidden="true" className="mx-auto max-w-6xl animate-pulse px-4 py-16 motion-reduce:animate-none sm:px-6 lg:px-8">
      <div className="h-10 w-64 rounded-lg bg-ink-800" />
      <div className="mt-6 h-5 w-96 max-w-full rounded bg-ink-850" />
      <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-48 rounded-2xl border border-ink-800 bg-ink-900" />
        ))}
      </div>
    </div>
  );
}
