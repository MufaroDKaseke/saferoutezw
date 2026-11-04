"use client";

import { useI18n } from "@/lib/i18n/provider";

/** "Loading…" in the reader's language, for Suspense fallbacks that cannot read the language themselves. */
export function LoadingText({ className = "text-sm text-slate-500" }: { className?: string }) {
  const { t } = useI18n();
  return <p className={className}>{t("common.loading")}</p>;
}
