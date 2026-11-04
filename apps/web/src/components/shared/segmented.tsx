"use client";

import { cn } from "@/lib/utils";

/** A compact single-choice control for things like a time range. */
export function SegmentedControl<T extends string>({
  label,
  value,
  onChange,
  options,
  className,
}: {
  label: string;
  value: T;
  onChange: (value: T) => void;
  options: readonly { value: T; label: string }[];
  className?: string;
}) {
  return (
    <div role="group" aria-label={label} className={cn("inline-flex rounded-lg bg-slate-100 p-1", className)}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(o.value)}
            className={cn(
              "h-9 rounded-md px-3.5 text-sm font-semibold whitespace-nowrap transition-colors focus-visible:outline-2",
              active ? "bg-slate-900 text-white shadow-sm" : "text-slate-700 hover:bg-white",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
