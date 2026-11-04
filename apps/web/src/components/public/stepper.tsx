"use client";

import { Check } from "lucide-react";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

/** Progress through a short flow. Always readable as text: "Step 2 of 3: Verify". */
export function Stepper({ steps, current }: { steps: string[]; current: number }) {
  const { t } = useI18n();
  return (
    <nav aria-label={t("stepper.progress")}>
      <p className="sr-only">{t("stepper.stepOf", { current: current + 1, total: steps.length, label: steps[current] })}</p>
      <ol className="flex items-center gap-2 sm:gap-3" aria-hidden>
        {steps.map((label, i) => {
          const done = i < current;
          const on = i === current;
          return (
            <li key={label} className="flex items-center gap-2 sm:gap-3 [&:not(:last-child)]:flex-1">
              <span
                className={cn(
                  "flex size-7 shrink-0 items-center justify-center rounded-full text-[13px] font-bold",
                  done ? "bg-slate-900 text-white" : on ? "bg-emerald-700 text-white" : "bg-slate-200 text-slate-700",
                )}
              >
                {done ? <Check className="size-4" /> : i + 1}
              </span>
              <span className={cn("text-sm font-semibold whitespace-nowrap", on ? "text-slate-900" : "text-slate-600", !on && "hidden sm:inline")}>{label}</span>
              {i < steps.length - 1 ? <span className="h-0.5 min-w-4 flex-1 rounded bg-slate-200" /> : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
