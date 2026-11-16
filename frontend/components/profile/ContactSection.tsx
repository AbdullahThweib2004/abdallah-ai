import { EnglishContent } from "@/components/ui/EnglishContent";
import type { Dictionary } from "@/lib/i18n/config";
import type { ContactLink, LinkKind } from "@/services/types";

const ICONS: Record<LinkKind, string> = {
  github: "M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.7c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.9 1.52 2.34 1.08 2.91.83.09-.65.35-1.08.63-1.33-2.22-.25-4.55-1.11-4.55-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02a9.6 9.6 0 0 1 5 0c1.91-1.29 2.75-1.02 2.75-1.02.55 1.37.2 2.39.1 2.64.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.68-4.57 4.93.36.31.68.92.68 1.85v2.75c0 .27.18.58.69.48A10 10 0 0 0 12 2Z",
  linkedin: "M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5ZM3 9.75h4v11H3v-11Zm6.5 0h3.83v1.5h.05c.53-1 1.84-2.05 3.79-2.05 4.05 0 4.8 2.67 4.8 6.13v5.42h-4v-4.8c0-1.15-.02-2.62-1.6-2.62-1.6 0-1.84 1.25-1.84 2.54v4.88h-4v-11Z",
  email: "M3 5h18a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Zm1.5 2v.3l7.5 5.2 7.5-5.2V7h-15Zm15 2.73-7.5 5.2-7.5-5.2V17h15V9.73Z",
  demo: "M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm4 5v8l7-4-7-4Z",
  other: "M10.6 13.4a1 1 0 0 0 1.4 0l4.6-4.6a3 3 0 0 0-4.2-4.2l-1.5 1.5 1.4 1.4 1.5-1.5a1 1 0 0 1 1.4 1.4L10.6 12a1 1 0 0 0 0 1.4Zm2.8-2.8a1 1 0 0 0-1.4 0l-4.6 4.6a3 3 0 0 0 4.2 4.2l1.5-1.5-1.4-1.4-1.5 1.5a1 1 0 0 1-1.4-1.4l4.6-4.6a1 1 0 0 0 0-1.4Z",
};

function displayUrl(url: string): string {
  return url.replace(/^mailto:/, "").replace(/^https:\/\/(www\.)?/, "").replace(/\/$/, "");
}

export function ContactSection({ links, t }: { links: ContactLink[]; t: Dictionary }) {
  return (
    <>
      <p className="mb-8 text-mist-200">{t.contact.intro}</p>
      <ul className="grid gap-4 sm:grid-cols-3">
        {links.map((link) => {
          const external = link.kind !== "email";
          return (
            <li key={link.link_id}>
              <a
                href={link.url}
                {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                className="group flex h-full items-center gap-4 rounded-2xl border border-ink-700 bg-ink-900 p-5 transition-colors hover:border-accent/60"
              >
                <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-ink-800 text-mist-50 transition-colors group-hover:bg-accent group-hover:text-accent-ink">
                  <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5" fill="currentColor">
                    <path d={ICONS[link.kind]} />
                  </svg>
                </span>
                <EnglishContent as="span" className="min-w-0">
                  <span className="block font-medium text-mist-50">{link.label}</span>
                  <span className="block truncate text-sm text-mist-400">{displayUrl(link.url)}</span>
                </EnglishContent>
                {external && <span className="sr-only">({t.contact.opensInNewTab})</span>}
              </a>
            </li>
          );
        })}
      </ul>
    </>
  );
}
