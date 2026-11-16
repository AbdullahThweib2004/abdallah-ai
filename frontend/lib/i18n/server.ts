import "server-only";

import { cookies } from "next/headers";

import { DEFAULT_LOCALE, type Locale, LOCALE_COOKIE, isLocale } from "./config";

/** The visitor's UI language, from the locale cookie set by the language switcher. */
export async function getLocale(): Promise<Locale> {
  const value = (await cookies()).get(LOCALE_COOKIE)?.value;
  return isLocale(value) ? value : DEFAULT_LOCALE;
}
