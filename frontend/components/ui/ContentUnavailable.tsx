import type { Dictionary } from "@/lib/i18n/config";

export function ContentUnavailable({ t }: { t: Dictionary }) {
  return (
    <div role="status" className="rounded-2xl border border-dashed border-ink-600 bg-ink-900/60 p-6 sm:p-8">
      <p className="font-medium text-mist-50">{t.unavailable.title}</p>
      <p className="mt-2 text-sm text-mist-400">{t.unavailable.body}</p>
    </div>
  );
}
