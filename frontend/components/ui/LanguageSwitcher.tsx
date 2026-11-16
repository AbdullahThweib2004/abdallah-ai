"use client";

import { useTransition } from "react";

import { setLocale } from "@/lib/i18n/actions";
import { type Locale, LOCALE_NAMES, LOCALES, directionOf } from "@/lib/i18n/config";

type Props = {
  locale: Locale;
  label: string;
  names: Record<Locale, string>;
};

export function LanguageSwitcher({ locale, label, names }: Props) {
  const [pending, startTransition] = useTransition();

  function choose(next: Locale) {
    if (next === locale) return;
    // Flip direction right away; the server re-render then swaps the UI strings.
    document.documentElement.setAttribute("lang", next);
    document.documentElement.setAttribute("dir", directionOf(next));
    startTransition(() => setLocale(next));
  }

  return (
    <div
      role="group"
      aria-label={label}
      aria-busy={pending}
      className="flex items-center rounded-full border border-ink-700 bg-ink-900 p-0.5"
    >
      {LOCALES.map((option) => (
        <button
          key={option}
          type="button"
          lang={option}
          aria-label={`${names[option]} – ${LOCALE_NAMES[option]}`}
          aria-pressed={option === locale}
          onClick={() => choose(option)}
          className={`min-w-10 rounded-full px-3 py-1 text-sm font-medium transition-colors ${
            option === locale ? "bg-accent text-accent-ink" : "text-mist-200 hover:text-mist-50"
          }`}
        >
          {names[option]}
        </button>
      ))}
    </div>
  );
}
