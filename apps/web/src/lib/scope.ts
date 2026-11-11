/**
 * Regional scope of this deployment. Everything defaults to the national (Zimbabwe-wide) service;
 * the Bulawayo / NUST version sets NEXT_PUBLIC_SCOPE_NAME, NEXT_PUBLIC_MAP_BOUNDS,
 * NEXT_PUBLIC_MAP_MIN_ZOOM and NEXT_PUBLIC_PROVINCES at build time.
 *
 * NEXT_PUBLIC_* variables are inlined by Next only when written out literally, so each one is read
 * here with its full name.
 */

export type LatLngBounds = [[number, number], [number, number]];

/** "south,west,north,east" in degrees, or null when absent or malformed. */
export function parseBounds(raw: string | undefined): LatLngBounds | null {
  if (!raw) return null;
  const parts = raw.split(",").map((p) => Number(p.trim()));
  if (parts.length !== 4 || parts.some((p) => !Number.isFinite(p))) return null;
  const [south, west, north, east] = parts;
  if (south >= north || west >= east || Math.abs(south) > 90 || Math.abs(north) > 90 || Math.abs(west) > 180 || Math.abs(east) > 180) {
    return null;
  }
  return [
    [south, west],
    [north, east],
  ];
}

/** Comma-separated list, trimmed; null when absent or empty (meaning "no restriction"). */
export function parseList(raw: string | undefined): string[] | null {
  const items = (raw ?? "")
    .split(",")
    .map((p) => p.trim())
    .filter(Boolean);
  return items.length ? items : null;
}

/** Room around the region the map may be panned into, in degrees. */
export function padBounds(bounds: LatLngBounds, degrees: number): LatLngBounds {
  return [
    [bounds[0][0] - degrees, bounds[0][1] - degrees],
    [bounds[1][0] + degrees, bounds[1][1] + degrees],
  ];
}

export const SCOPE_NAME: string = process.env.NEXT_PUBLIC_SCOPE_NAME?.trim() || "Zimbabwe";

/** The region's map frame, or null for the national default (each map keeps its own Zimbabwe frame). */
export const REGION_BOUNDS: LatLngBounds | null = parseBounds(process.env.NEXT_PUBLIC_MAP_BOUNDS);

export const MAP_MIN_ZOOM: number = (() => {
  const zoom = Number(process.env.NEXT_PUBLIC_MAP_MIN_ZOOM);
  return Number.isFinite(zoom) && zoom >= 1 && zoom <= 18 ? zoom : 5;
})();

/** Provinces offered in pickers, or null for all ten. */
export const SCOPE_PROVINCES: string[] | null = parseList(process.env.NEXT_PUBLIC_PROVINCES);

export function limitProvinces<T extends string>(all: readonly T[]): T[] {
  return SCOPE_PROVINCES ? all.filter((p) => SCOPE_PROVINCES.includes(p)) : [...all];
}
