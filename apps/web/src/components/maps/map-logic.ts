import type { Incident } from "@/types";

/**
 * The map keeps four layers apart, because they mean different things:
 *   reported  = internal, unverified candidates (never for a public map)
 *   reviewed  = an editor has looked and asked for changes; not approved
 *   approved  = an approved public alert exists (approval is not delivery)
 *   blackspot = historical risk context, never evidence of a new incident
 * Rejected incidents are never plotted.
 */
export type MarkerKind = "reported" | "reviewed" | "approved";

export function markerKind(incident: Pick<Incident, "id" | "reviewState">, alertIncidentIds: ReadonlySet<string>): MarkerKind {
  if (alertIncidentIds.has(incident.id) || incident.reviewState === "approved") return "approved";
  if (incident.reviewState === "needs_changes") return "reviewed";
  return "reported";
}

export interface MapLayers {
  reported: boolean;
  reviewed: boolean;
  approved: boolean;
  blackspots: boolean;
  clusters: boolean;
}

export const DEFAULT_LAYERS: MapLayers = {
  reported: true,
  reviewed: true,
  approved: true,
  blackspots: true,
  clusters: false,
};

/** Approximate uncertainty radius, in metres, for each position accuracy. */
export const ACCURACY_RADIUS_M = {
  exact: 100,
  road_segment: 1000,
  approximate: 3000,
  town: 5000,
} as const;

/* ---------------------------------------------------------------- clusters */

export interface ClusterInput {
  id: string;
  lat: number;
  lng: number;
}

export interface Cluster<T extends ClusterInput> {
  key: string;
  lat: number;
  lng: number;
  members: T[];
}

/** Web Mercator pixel position at a zoom level (256px tiles). */
export function project(lat: number, lng: number, zoom: number): { x: number; y: number } {
  const scale = 256 * 2 ** zoom;
  const sin = Math.min(0.9999, Math.max(-0.9999, Math.sin((lat * Math.PI) / 180)));
  return {
    x: ((lng + 180) / 360) * scale,
    y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale,
  };
}

/**
 * Group nearby points into grid cells of `cellPx` screen pixels. Cheap, stable
 * and good enough for tens to a few hundred points. Single points stay single.
 */
export function clusterPoints<T extends ClusterInput>(points: readonly T[], zoom: number, cellPx = 56): Cluster<T>[] {
  const cells = new Map<string, T[]>();
  for (const p of points) {
    const { x, y } = project(p.lat, p.lng, zoom);
    const key = `${Math.floor(x / cellPx)}:${Math.floor(y / cellPx)}`;
    const bucket = cells.get(key);
    if (bucket) bucket.push(p);
    else cells.set(key, [p]);
  }
  return Array.from(cells.entries()).map(([key, members]) => ({
    key: members.length === 1 ? members[0].id : `cluster-${key}`,
    lat: members.reduce((s, m) => s + m.lat, 0) / members.length,
    lng: members.reduce((s, m) => s + m.lng, 0) / members.length,
    members,
  }));
}
