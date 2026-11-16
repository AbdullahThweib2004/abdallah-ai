import Link from "next/link";

export function TalkCta({ label }: { label: string }) {
  return (
    <Link
      href="/"
      className="inline-flex items-center gap-2 rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-strong"
    >
      {label}
      <span aria-hidden="true" className="rtl:rotate-180">
        →
      </span>
    </Link>
  );
}
