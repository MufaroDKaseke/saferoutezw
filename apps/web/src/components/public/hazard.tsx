import { CircleAlert, Info, OctagonAlert, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import { BLACKSPOT, GLYPHS, glyphFor, severityStyle, type GlyphName } from "@/lib/public-api/hazard-style";
import { HAZARD_LABELS } from "@/lib/public-api/client";

/** One hazard icon, drawn from the shared glyph set (also used by the map markers). */
export function HazardGlyph({ name, className }: { name: GlyphName; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={cn("size-5 shrink-0", className)}
      dangerouslySetInnerHTML={{ __html: GLYPHS[name] }}
    />
  );
}

/** Tinted square holding the hazard icon. Decorative: the label next to it carries the meaning. */
export function HazardTile({
  hazardType,
  severity = "unknown",
  blackspot = false,
  className,
}: {
  hazardType: string;
  severity?: string;
  blackspot?: boolean;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-11 shrink-0 items-center justify-center rounded-xl",
        blackspot ? BLACKSPOT.tile : severityStyle(severity).tile,
        className,
      )}
    >
      <HazardGlyph name={blackspot ? "target" : glyphFor(hazardType)} className="size-6" />
    </span>
  );
}

const SEVERITY_ICON = { fatal: OctagonAlert, serious: TriangleAlert, minor: CircleAlert, unknown: Info } as const;

/** Severity as icon + word + colour, so it never depends on colour alone. */
export function SeverityBadge({ severity, className }: { severity: string; className?: string }) {
  const style = severityStyle(severity);
  const key = (severity in SEVERITY_ICON ? severity : "unknown") as keyof typeof SEVERITY_ICON;
  const Icon = SEVERITY_ICON[key];
  return (
    <span
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-lg pr-2.5 pl-2 text-[12.5px] font-bold whitespace-nowrap",
        style.badge,
        className,
      )}
    >
      <Icon className="size-4" aria-hidden />
      {style.label}
    </span>
  );
}

export function HazardTag({ hazardType, className }: { hazardType: string; className?: string }) {
  return (
    <span className={cn("inline-flex h-7 items-center rounded-lg bg-slate-100 px-2.5 text-[12.5px] font-semibold text-slate-700", className)}>
      {HAZARD_LABELS[hazardType] ?? hazardType}
    </span>
  );
}
