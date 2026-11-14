export type Locale = "en" | "ar";
export type Direction = "ltr" | "rtl";

const DIRECTIONS: Record<Locale, Direction> = {
  en: "ltr",
  ar: "rtl",
};

function isLocale(value: string | undefined): value is Locale {
  return value !== undefined && value in DIRECTIONS;
}

const envLocale = process.env.NEXT_PUBLIC_DEFAULT_LOCALE;

export const localeConfig: { lang: Locale; dir: Direction } = (() => {
  const lang: Locale = isLocale(envLocale) ? envLocale : "en";
  return { lang, dir: DIRECTIONS[lang] };
})();
