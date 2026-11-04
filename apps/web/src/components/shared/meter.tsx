import { cn } from "@/lib/utils";

/**
 * Segmented meter from the concept. It always sits beside a word label (for
 * example "Moderate"), so the level never depends on colour.
 */
export function SegmentMeter({
  filled,
  total = 5,
  tone = "navy",
  label,
  className,
}: {
  filled: number;
  total?: number;
  tone?: "navy" | "red" | "indigo";
  label: string;
  className?: string;
}) {
  const fill = tone === "red" ? "bg-red-600" : tone === "indigo" ? "bg-indigo-500" : "bg-slate-700";
  return (
    <div
      role="img"
      aria-label={`${label}: ${filled} of ${total}`}
      className={cn("flex gap-1", className)}
    >
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={cn("h-1.5 flex-1 rounded-full", i < filled ? fill : "bg-slate-200")} />
      ))}
    </div>
  );
}

/** Compact bar used in tables: extraction confidence with its percentage. */
export function ConfidenceBar({ value, className }: { value: number | null | undefined; className?: string }) {
  if (value == null) return <span className="text-muted-foreground">–</span>;
  const pct = Math.round(value * 100);
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-slate-200" aria-hidden>
        <span className="block h-full rounded-full bg-slate-700" style={{ width: `${pct}%` }} />
      </span>
      <span className="tnum text-sm font-medium">{pct}%</span>
    </div>
  );
}
