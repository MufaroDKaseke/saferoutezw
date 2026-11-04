"use client";

import { useId } from "react";
import { Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

const ALL = "__all__";

/** Small label above a control, as in the concept's filter bars. */
export function FilterField({
  label,
  htmlFor,
  className,
  children,
}: {
  label: string;
  htmlFor?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <label htmlFor={htmlFor} className="text-xs font-medium text-slate-600">
        {label}
      </label>
      {children}
    </div>
  );
}

export function SearchField({
  label,
  value,
  onChange,
  placeholder,
  className,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}) {
  const id = useId();
  return (
    <FilterField label={label} htmlFor={id} className={className}>
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
        <Input
          id={id}
          type="search"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="pl-9"
          autoComplete="off"
        />
      </div>
    </FilterField>
  );
}

export interface Option<T extends string> {
  value: T;
  label: string;
}

export function SelectField<T extends string>({
  label,
  value,
  onChange,
  options,
  allLabel = "All",
  className,
}: {
  label: string;
  value: T | undefined;
  onChange: (value: T | undefined) => void;
  options: readonly Option<T>[];
  allLabel?: string;
  className?: string;
}) {
  const id = useId();
  return (
    <FilterField label={label} htmlFor={id} className={className}>
      <Select value={value ?? ALL} onValueChange={(v) => onChange(v === ALL ? undefined : (v as T))}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent position="popper">
          <SelectItem value={ALL}>{allLabel}</SelectItem>
          {options.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </FilterField>
  );
}

/** A responsive row of filters with a clear button that only appears when something is set. */
export function FilterBar({
  children,
  onClear,
  canClear,
  className,
}: {
  children: React.ReactNode;
  onClear?: () => void;
  canClear?: boolean;
  className?: string;
}) {
  return (
    <div
      role="search"
      className={cn(
        "grid items-end gap-3 rounded-xl bg-card p-4 ring-1 ring-foreground/10 sm:grid-cols-2 lg:grid-cols-[repeat(auto-fit,minmax(150px,1fr))]",
        className,
      )}
    >
      {children}
      {onClear ? (
        <Button variant="outline" onClick={onClear} disabled={!canClear} className="h-10 self-end">
          <X aria-hidden /> Clear filters
        </Button>
      ) : null}
    </div>
  );
}

export const RANGE_OPTIONS = [
  { value: "24h", label: "Last 24 hours" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
] as const;
