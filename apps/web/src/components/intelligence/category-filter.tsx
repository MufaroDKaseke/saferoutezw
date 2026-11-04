"use client";

import { CATEGORY_FILTERS } from "@/lib/domain/intelligence";
import type { PrimaryCategory } from "@/lib/taxonomy.generated";
import { cn } from "@/lib/utils";

export type CategoryFilterValue = "all" | PrimaryCategory;

/** Single-choice category chips. Wraps on small screens so every option stays reachable. */
export function CategoryFilter({
  value,
  onChange,
  counts,
  className,
}: {
  value: CategoryFilterValue;
  onChange: (value: CategoryFilterValue) => void;
  /** Optional per-category totals shown beside each label. */
  counts?: Partial<Record<CategoryFilterValue, number>>;
  className?: string;
}) {
  return (
    <div role="group" aria-label="Filter by category" className={cn("flex flex-wrap gap-2", className)}>
      {CATEGORY_FILTERS.map((option) => {
        const active = option.value === value;
        const count = counts?.[option.value];
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "inline-flex h-9 items-center gap-1.5 rounded-full border px-3.5 text-sm font-semibold whitespace-nowrap transition-colors focus-visible:outline-2",
              active
                ? "border-slate-900 bg-slate-900 text-white"
                : "border-slate-300 bg-white text-slate-700 hover:border-slate-500 hover:bg-slate-50",
            )}
          >
            {option.label}
            {count !== undefined ? <span className={cn("tnum text-xs", active ? "text-slate-300" : "text-slate-500")}>{count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
