import { ar } from "./ar";
import { type Dictionary, en } from "./en";

export type Locale = "en" | "ar";
export type Direction = "ltr" | "rtl";

export const LOCALES: readonly Locale[] = ["en", "ar"];
export const LOCALE_COOKIE = "locale";

const DIRECTIONS: Record<Locale, Direction> = { en: "ltr", ar: "rtl" };

/** Each language's name in its own language (used as the switcher's accessible names). */
export const LOCALE_NAMES: Record<Locale, string> = { en: "English", ar: "العربية" };
const DICTIONARIES: Record<Locale, Dictionary> = { en, ar };

export function isLocale(value: string | undefined): value is Locale {
  return value !== undefined && (LOCALES as readonly string[]).includes(value);
}

const envLocale = process.env.NEXT_PUBLIC_DEFAULT_LOCALE;
export const DEFAULT_LOCALE: Locale = isLocale(envLocale) ? envLocale : "en";

export function directionOf(locale: Locale): Direction {
  return DIRECTIONS[locale];
}

export function getDictionary(locale: Locale): Dictionary {
  return DICTIONARIES[locale];
}

export type { Dictionary };
