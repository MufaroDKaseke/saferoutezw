"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import type { MapLayers } from "./map-logic";

const TOGGLES: { key: keyof MapLayers; label: string }[] = [
  { key: "reported", label: "Reported, unverified" },
  { key: "reviewed", label: "Reviewed" },
  { key: "approved", label: "Approved alerts" },
  { key: "blackspots", label: "Blackspots" },
  { key: "clusters", label: "Cluster markers" },
];

/** Layer toggles. Each is a real checkbox, so state is announced and keyboard operable. */
export function LayerToggles({
  layers,
  onChange,
  className,
}: {
  layers: MapLayers;
  onChange: (next: MapLayers) => void;
  className?: string;
}) {
  return (
    <fieldset className={cn("flex flex-wrap gap-2", className)}>
      <legend className="sr-only">Map layers</legend>
      {TOGGLES.map(({ key, label }) => (
        <label
          key={key}
          className={cn(
            "inline-flex h-11 cursor-pointer items-center gap-2 rounded-lg border px-3.5 text-sm font-semibold transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-emerald-600",
            layers[key] ? "border-slate-900 bg-slate-900 text-white" : "border-border bg-card text-slate-800 hover:bg-slate-50",
          )}
        >
          <input
            type="checkbox"
            className="sr-only"
            checked={layers[key]}
            onChange={(e) => onChange({ ...layers, [key]: e.target.checked })}
          />
          <span
            className={cn(
              "flex size-[18px] items-center justify-center rounded border",
              layers[key] ? "border-emerald-400 bg-emerald-500 text-slate-950" : "border-slate-400 bg-white",
            )}
            aria-hidden
          >
            {layers[key] ? <Check className="size-3.5" strokeWidth={3.5} /> : null}
          </span>
          {label}
        </label>
      ))}
    </fieldset>
  );
}

/** Legend, written out in words as well as symbols. */
export function MapLegend({ className, inline = false }: { className?: string; inline?: boolean }) {
  return (
    <div
      className={cn(
        inline ? "text-xs" : "rounded-lg bg-card/95 px-3.5 py-3 text-xs shadow-md ring-1 ring-foreground/10",
        className,
      )}
    >
      <p className={cn("section-label", inline ? "mb-1.5" : "mb-2")}>Legend</p>
      <ul className={cn("text-slate-800", inline ? "flex flex-wrap gap-x-4 gap-y-1.5" : "space-y-1.5")}>
        <li className="flex items-center gap-2">
          <span className="flex size-4 items-center justify-center rounded-full border-[3px] border-amber-500 bg-white text-[9px] font-bold text-amber-700" aria-hidden>
            !
          </span>
          Reported, unverified (internal)
        </li>
        <li className="flex items-center gap-2">
          <span className="flex size-4 items-center justify-center rounded-full border-[3px] border-slate-900 bg-white" aria-hidden>
            <span className="size-1.5 rounded-full bg-slate-900" />
          </span>
          Reviewed, changes requested
        </li>
        <li className="flex items-center gap-2">
          <span className="flex size-4 items-center justify-center rounded-full bg-emerald-600 text-white" aria-hidden>
            <Check className="size-2.5" strokeWidth={4} />
          </span>
          Approved alert (approval is not delivery)
        </li>
        <li className="flex items-center gap-2">
          <span className="flex size-4 items-center justify-center rounded-full bg-slate-900 text-[9px] font-bold text-white" aria-hidden>
            3
          </span>
          Cluster of nearby reports
        </li>
        <li className="flex items-center gap-2">
          <span className="size-4 rounded-full border-2 border-dashed border-red-600 bg-red-500/15" aria-hidden />
          Historical blackspot (demo, synthetic)
        </li>
      </ul>
    </div>
  );
}
