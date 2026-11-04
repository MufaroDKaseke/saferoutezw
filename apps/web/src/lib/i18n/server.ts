import { cookies } from "next/headers";
import { cache } from "react";
import { DEFAULT_LOCALE, LOCALE_COOKIE, isLocale, type Locale } from "./config";
import { MESSAGES } from "./messages";
import { createTranslator, type Translator } from "./translate";

/**
 * The visitor's chosen language. Reads the request cookie, so the caller must sit under a Suspense
 * boundary (the public layout provides one).
 */
export const getLocale = cache(async (): Promise<Locale> => {
  const value = (await cookies()).get(LOCALE_COOKIE)?.value;
  return isLocale(value) ? value : DEFAULT_LOCALE;
});

/** Translator for server components. Client components use `useI18n()` instead. */
export async function getI18n(): Promise<Translator> {
  const locale = await getLocale();
  return createTranslator(locale, MESSAGES[locale]);
}
