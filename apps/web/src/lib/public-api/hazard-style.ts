/**
 * Visual language for published hazards: one icon per hazard type, one style per severity.
 * Pure data (no React) so the Leaflet marker code and the React components share it.
 *
 * Severity comes from the editor-approved value on the alert. It is never inferred from hazard type.
 * Colour is always paired with an icon and a word: see SeverityBadge.
 */

/** Inner SVG markup for a 24x24 stroke icon (Lucide-style, 2px stroke). Static, trusted constants. */
export const GLYPHS = {
  car: '<path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/><circle cx="7" cy="17" r="2"/><path d="M9 17h6"/><circle cx="17" cy="17" r="2"/>',
  person: '<circle cx="12" cy="5" r="1"/><path d="m9 20 3-6 3 6"/><path d="m6 8 6 2 6-2"/><path d="M12 10v4"/>',
  truck:
    '<path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><path d="M15 18H9"/><path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.624l-3.48-4.35A1 1 0 0 0 17.52 8H14"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/>',
  flame:
    '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
  wrench:
    '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.1-3.1a6 6 0 0 1-8.3 7.1l-7.9 7.9a1 1 0 0 1-3-3l7.9-7.9a6 6 0 0 1 7.1-8.3z"/>',
  warning:
    '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  ban: '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
  cone: '<rect x="2" y="6" width="20" height="8" rx="1"/><path d="M17 14v7M7 14v7M17 3v3M7 3v3M10 14 2.3 6.3M14 6l7.7 7.7M8 6l8 8"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
  target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
} as const;

export type GlyphName = keyof typeof GLYPHS;

export const HAZARD_GLYPH: Record<string, GlyphName> = {
  collision: "car",
  pedestrian_strike: "person",
  rollover: "truck",
  vehicle_fire: "flame",
  breakdown: "wrench",
  road_hazard: "warning",
  road_closure: "ban",
  traffic_disruption: "cone",
  other: "info",
  blackspot: "target",
};

export function glyphFor(hazardType: string): GlyphName {
  return HAZARD_GLYPH[hazardType] ?? "info";
}

export type SeverityKey = "fatal" | "serious" | "minor" | "unknown";

export interface SeverityStyle {
  label: string;
  /** Short plain-language meaning, shown in the severity guide. */
  meaning: string;
  /** Solid or outlined pill. Differs in lightness as well as hue. */
  badge: string;
  /** Tinted tile behind the hazard icon. */
  tile: string;
  /** Marker colours for the map. */
  marker: { fill: string; glyph: string; edge: string };
}

export const SEVERITY: Record<SeverityKey, SeverityStyle> = {
  fatal: {
    label: "Fatal",
    meaning: "A death was reported. Expect serious disruption.",
    badge: "bg-red-700 text-white",
    tile: "bg-red-100 text-red-800",
    marker: { fill: "#b91c1c", glyph: "#ffffff", edge: "#ffffff" },
  },
  serious: {
    label: "Serious",
    meaning: "Serious injury or major disruption reported.",
    badge: "bg-amber-400 text-slate-900",
    tile: "bg-amber-100 text-amber-900",
    marker: { fill: "#fbbf24", glyph: "#0f172a", edge: "#ffffff" },
  },
  minor: {
    label: "Minor",
    meaning: "Slow down and allow extra time.",
    badge: "bg-amber-50 text-amber-900 ring-1 ring-inset ring-amber-400",
    tile: "bg-amber-50 text-amber-800",
    marker: { fill: "#fef3c7", glyph: "#78350f", edge: "#d97706" },
  },
  unknown: {
    label: "Not rated",
    meaning: "The editor has not rated this notice.",
    badge: "bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-300",
    tile: "bg-slate-100 text-slate-700",
    marker: { fill: "#e2e8f0", glyph: "#334155", edge: "#64748b" },
  },
};

export function severityStyle(severity: string): SeverityStyle {
  return SEVERITY[(severity in SEVERITY ? severity : "unknown") as SeverityKey];
}

/** Historical blackspots are always indigo and dashed so past risk is never read as a current alert. */
export const BLACKSPOT = {
  tile: "bg-indigo-100 text-indigo-800",
  card: "border-dashed border-indigo-300 bg-indigo-50/60",
  marker: { fill: "#e0e7ff", glyph: "#3730a3", edge: "#4f46e5" },
};

export type MarkerKind = "alert" | "blackspot" | "stop";

/**
 * HTML for a Leaflet divIcon. Shape tells the category (octagon = closure, diamond = traffic
 * disruption, dashed ring = historical blackspot), fill tells severity, glyph tells the hazard.
 */
export function markerHtml(kind: MarkerKind, hazardType: string, severity: string, approximate = false): string {
  if (kind === "stop") {
    return '<svg viewBox="-14 -14 28 28" width="28" height="28" aria-hidden="true"><circle r="9" fill="#fff" stroke="#047857" stroke-width="5"/></svg>';
  }
  const c = kind === "blackspot" ? BLACKSPOT.marker : severityStyle(severity).marker;
  const glyph = GLYPHS[kind === "blackspot" ? "target" : glyphFor(hazardType)];
  const opacity = approximate ? 0.7 : 1;
  let shape: string;
  if (kind === "blackspot") {
    shape = `<circle r="17" fill="${c.fill}" stroke="${c.edge}" stroke-width="2.5" stroke-dasharray="4 3"/>`;
  } else if (hazardType === "road_closure") {
    shape = `<polygon points="-6.5,-16 6.5,-16 16,-6.5 16,6.5 6.5,16 -6.5,16 -16,6.5 -16,-6.5" fill="${c.fill}" stroke="${c.edge}" stroke-width="3"/>`;
  } else if (hazardType === "traffic_disruption") {
    shape = `<rect x="-13" y="-13" width="26" height="26" rx="5" transform="rotate(45)" fill="${c.fill}" stroke="${c.edge}" stroke-width="3"/>`;
  } else {
    shape = `<circle r="15" fill="${c.fill}" stroke="${c.edge}" stroke-width="3"${approximate ? ' stroke-dasharray="4 3"' : ""}/>`;
  }
  return (
    `<svg viewBox="-20 -20 40 40" width="40" height="40" aria-hidden="true" style="opacity:${opacity}">${shape}` +
    `<g transform="translate(-9 -9) scale(0.75)" fill="none" stroke="${c.glyph}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">${glyph}</g></svg>`
  );
}
