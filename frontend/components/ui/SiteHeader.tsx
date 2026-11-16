import Link from "next/link";

import type { Dictionary, Locale } from "@/lib/i18n/config";

import { LanguageSwitcher } from "./LanguageSwitcher";

export function SiteHeader({ t, locale }: { t: Dictionary; locale: Locale }) {
  const links = [
    { href: "/projects", label: t.nav.projects },
    { href: "/about", label: t.nav.about },
    { href: "/?card=contact", label: t.nav.contact },
  ];
  const languageNames = { en: t.language.en, ar: t.language.ar };

  return (
    <header className="sticky top-0 z-40 h-[var(--header-height)] border-b border-ink-800/80 bg-ink-950/80 backdrop-blur-md">
      <div className="mx-auto flex h-full max-w-6xl items-center gap-6 px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-2.5 font-semibold tracking-tight text-mist-50">
          <span aria-hidden="true" className="grid size-7 place-items-center rounded-lg bg-accent font-mono text-sm text-accent-ink">
            A
          </span>
          <span lang="en">{t.brand}</span>
        </Link>

        <nav aria-label={t.nav.label} className="ms-auto hidden md:block">
          <ul className="flex items-center gap-1">
            {links.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  className="rounded-md px-3 py-2 text-sm text-mist-200 transition-colors hover:text-mist-50"
                >
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="ms-auto flex items-center gap-3 md:ms-0">
          <LanguageSwitcher locale={locale} label={t.language.label} names={languageNames} />

          <details className="group relative md:hidden">
            <summary className="flex cursor-pointer list-none items-center rounded-md border border-ink-700 px-3 py-1.5 text-sm text-mist-200 [&::-webkit-details-marker]:hidden">
              {t.nav.menu}
            </summary>
            <nav
              aria-label={t.nav.label}
              className="absolute end-0 top-full mt-2 w-48 rounded-xl border border-ink-700 bg-ink-900 p-2 shadow-2xl"
            >
              <ul>
                {links.map((link) => (
                  <li key={link.href}>
                    <Link href={link.href} className="block rounded-md px-3 py-2 text-sm text-mist-200 hover:bg-ink-800 hover:text-mist-50">
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          </details>
        </div>
      </div>
    </header>
  );
}
