export function SectionHeading({ id, index, title }: { id: string; index: string; title: string }) {
  return (
    <div className="mb-10 flex items-baseline gap-4">
      <span aria-hidden="true" className="font-mono text-sm text-accent">
        {index}
      </span>
      <h2 id={id} className="text-2xl font-semibold tracking-tight text-mist-50 sm:text-3xl">
        {title}
      </h2>
      <span aria-hidden="true" className="h-px flex-1 self-center bg-ink-700" />
    </div>
  );
}
