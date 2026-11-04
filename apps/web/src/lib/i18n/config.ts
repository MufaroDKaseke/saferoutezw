/**
 * Languages offered on the public site. The choice is kept in a cookie (not in the URL) so every
 * address stays the same and the server can render the right language on the first paint.
 */
export const LOCALES = ["en", "sn", "nd"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_COOKIE = "srzw_lang";
export const LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

/** Each language is named in itself, so a reader can find it without reading English. */
export const LOCALE_NAMES: Record<Locale, string> = {
  en: "English",
  sn: "ChiShona",
  nd: "isiNdebele",
};

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

/** BCP 47 tag used for dates and numbers: language plus Zimbabwe. */
export function intlTag(locale: Locale): string {
  return `${locale}-ZW`;
}
