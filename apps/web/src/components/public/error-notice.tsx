"use client";

import { CircleAlert } from "lucide-react";
import { useI18n } from "@/lib/i18n/provider";

export function ErrorNotice({ message, title }: { message: string; title?: string }) {
  const { t } = useI18n();
  return (
    <div role="alert" className="flex gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
      <CircleAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
      <div>
        <p className="font-semibold">{title ?? t("common.errorTitle")}</p>
        <p>{message}</p>
      </div>
    </div>
  );
}
