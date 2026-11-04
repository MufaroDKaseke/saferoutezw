"use client";

import { useId, useTransition } from "react";
import { Globe, Loader2 } from "lucide-react";
import { LOCALES, LOCALE_NAMES, isLocale } from "@/lib/i18n/config";
import { setLocale } from "@/lib/i18n/actions";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

/**
 * Language choice for the public site. A native select, so it is keyboard and screen-reader friendly and
 * costs no extra JavaScript. Each language is named in itself. Choosing one saves a cookie and re-renders
 * the page in place; the address does not change.
 */
export function LanguageSwitcher({ className, tone = "light" }: { className?: string; tone?: "light" | "dark" }) {
  const { locale, t } = useI18n();
  const id = useId();
  const [pending, startTransition] = useTransition();

  return (
    <div className={cn("relative inline-flex items-center", className)}>
      <label htmlFor={id} className="sr-only">
        {t("language.choose")}
      </label>
      {pending ? (
        <Loader2 className={cn("pointer-events-none absolute left-3 size-4 animate-spin", tone === "dark" ? "text-slate-300" : "text-slate-600")} aria-hidden />
      ) : (
        <Globe className={cn("pointer-events-none absolute left-3 size-4", tone === "dark" ? "text-slate-300" : "text-slate-600")} aria-hidden />
      )}
      <select
        id={id}
        value={locale}
        disabled={pending}
        onChange={(event) => {
          const next = event.target.value;
          if (isLocale(next)) startTransition(() => setLocale(next));
        }}
        className={cn(
          "h-11 cursor-pointer appearance-none rounded-lg border pr-3 pl-9 text-sm font-semibold outline-none focus-visible:ring-3 focus-visible:ring-emerald-600/40",
          tone === "dark"
            ? "border-slate-600 bg-slate-800 text-slate-100 hover:bg-slate-700"
            : "border-slate-300 bg-white text-slate-800 hover:bg-slate-100",
        )}
      >
        {LOCALES.map((code) => (
          <option key={code} value={code} lang={code}>
            {LOCALE_NAMES[code]}
          </option>
        ))}
      </select>
    </div>
  );
}
