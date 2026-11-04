"use client";

import { createContext, useContext, useMemo } from "react";
import type { Locale } from "./config";
import { en } from "./messages/en";
import { createTranslator, type Messages, type Translator } from "./translate";

// Without a provider (unit tests, isolated renders) text falls back to English.
const I18nContext = createContext<Translator>(createTranslator("en", en));

/** Receives only the active language's messages from the server, so the other languages are never downloaded. */
export function I18nProvider({ locale, messages, children }: { locale: Locale; messages: Messages; children: React.ReactNode }) {
  const value = useMemo(() => createTranslator(locale, messages), [locale, messages]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): Translator {
  return useContext(I18nContext);
}
