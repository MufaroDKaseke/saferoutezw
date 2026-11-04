"use client";

import { Check, Globe, MapPin } from "lucide-react";
import { cn } from "@/lib/utils";

/** A large radio card. The real radio input stays in the DOM, so it works with keyboard and screen readers. */
export function ChoiceCard({
  name,
  checked,
  onChange,
  title,
  hint,
  icon,
}: {
  name: string;
  checked: boolean;
  onChange: () => void;
  title: string;
  hint?: string;
  icon?: React.ReactNode;
}) {
  return (
    <label
      className={cn(
        "flex min-h-16 flex-1 cursor-pointer items-center gap-3 rounded-xl border-2 bg-white px-4 py-3 text-sm transition-colors has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-emerald-600/40",
        checked ? "border-emerald-700 bg-emerald-50" : "border-slate-300 hover:border-slate-400",
      )}
    >
      <input type="radio" name={name} checked={checked} onChange={onChange} className="peer sr-only" />
      <span
        aria-hidden
        className={cn("flex size-5 shrink-0 items-center justify-center rounded-full border-2", checked ? "border-emerald-700 bg-emerald-700" : "border-slate-400")}
      >
        {checked ? <span className="size-2 rounded-full bg-white" /> : null}
      </span>
      {icon ? <span aria-hidden className="text-slate-700">{icon}</span> : null}
      <span>
        <span className="block font-semibold text-slate-900">{title}</span>
        {hint ? <span className="block text-[13px] text-slate-600">{hint}</span> : null}
      </span>
    </label>
  );
}

function Chip({ checked, onChange, children }: { checked: boolean; onChange: () => void; children: React.ReactNode }) {
  return (
    <label
      className={cn(
        "inline-flex min-h-11 cursor-pointer items-center gap-1.5 rounded-full border px-4 text-sm font-semibold transition-colors has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-emerald-600/40",
        checked ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 bg-white text-slate-800 hover:bg-slate-100",
      )}
    >
      <input type="checkbox" checked={checked} onChange={onChange} className="sr-only" />
      {checked ? <Check className="size-4" aria-hidden /> : null}
      {children}
    </label>
  );
}

/**
 * "Which alerts?": all of Zimbabwe, or chosen provinces and corridors.
 * The detail only appears once "Choose areas" is selected, to keep the first screen short.
 */
export function AreaPicker({
  idPrefix,
  allZimbabwe,
  onAllChange,
  provinces,
  corridors,
  provinceOptions,
  corridorOptions,
  onToggle,
}: {
  idPrefix: string;
  allZimbabwe: boolean;
  onAllChange: (all: boolean) => void;
  provinces: string[];
  corridors: string[];
  provinceOptions: readonly string[];
  corridorOptions: readonly string[];
  onToggle: (key: "provinces" | "corridors", value: string) => void;
}) {
  return (
    <fieldset className="space-y-3">
      <legend className="mb-2 text-sm font-semibold">Which alerts?</legend>
      <div className="flex flex-col gap-3 sm:flex-row">
        <ChoiceCard name={`${idPrefix}-scope`} checked={allZimbabwe} onChange={() => onAllChange(true)} title="All of Zimbabwe" hint="Every published notice" icon={<Globe className="size-5" />} />
        <ChoiceCard name={`${idPrefix}-scope`} checked={!allZimbabwe} onChange={() => onAllChange(false)} title="Choose areas" hint="Provinces and roads you use" icon={<MapPin className="size-5" />} />
      </div>
      {!allZimbabwe ? (
        <div className="space-y-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div role="group" aria-labelledby={`${idPrefix}-prov`}>
            <p id={`${idPrefix}-prov`} className="mb-2 text-sm font-semibold">
              Provinces
            </p>
            <div className="flex flex-wrap gap-2">
              {provinceOptions.map((p) => (
                <Chip key={p} checked={provinces.includes(p)} onChange={() => onToggle("provinces", p)}>
                  {p}
                </Chip>
              ))}
            </div>
          </div>
          {corridorOptions.length ? (
            <div role="group" aria-labelledby={`${idPrefix}-cor`}>
              <p id={`${idPrefix}-cor`} className="mb-1 text-sm font-semibold">
                Major road corridors <span className="font-normal text-slate-600">(optional)</span>
              </p>
              {corridorOptions.map((c) => (
                <label key={c} className="flex min-h-11 cursor-pointer items-center gap-3 text-sm">
                  <input type="checkbox" className="size-5 accent-emerald-700" checked={corridors.includes(c)} onChange={() => onToggle("corridors", c)} />
                  {c}
                </label>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </fieldset>
  );
}
