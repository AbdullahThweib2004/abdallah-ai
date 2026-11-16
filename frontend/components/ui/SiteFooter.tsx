import type { Dictionary } from "@/lib/i18n/config";

import { BackendStatusBadge } from "./BackendStatusBadge";

export function SiteFooter({ t }: { t: Dictionary }) {
  return (
    <footer className="mt-24 border-t border-ink-800">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-10 text-sm text-mist-400 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
        <div>
          <p className="font-medium text-mist-200" lang="en">
            {t.brand}
          </p>
          <p className="mt-1 max-w-md">{t.footer.note}</p>
        </div>
        <BackendStatusBadge labels={t.footer.backend} />
      </div>
    </footer>
  );
}
