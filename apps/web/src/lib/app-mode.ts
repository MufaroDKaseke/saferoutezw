/**
 * Which product this build is: SafeRouteZW road safety (the default) or the NUST FM newsroom.
 *
 * Set NEXT_PUBLIC_APP_MODE=nust_newsroom at build time. Next only inlines NEXT_PUBLIC_* variables written
 * out literally, so the variable is read here with its full name, like `lib/scope.ts`. The backend has the
 * matching APP_MODE and refuses road-safety endpoints itself; this file only decides what the web app shows.
 */

export type AppMode = "road_safety" | "nust_newsroom";

export function parseAppMode(raw: string | undefined): AppMode {
  return raw?.trim() === "nust_newsroom" ? "nust_newsroom" : "road_safety";
}

export const APP_MODE: AppMode = parseAppMode(process.env.NEXT_PUBLIC_APP_MODE);
export const isNewsroomMode: boolean = APP_MODE === "nust_newsroom";

/** Pages that belong to the road-safety product. Hidden from navigation AND blocked by `src/proxy.ts`. */
export const ROAD_ROUTE_PREFIXES = [
  "/map",
  "/incidents",
  "/blackspots",
  "/alerts",
  "/reviews",
  "/intelligence",
  "/public",
] as const;

export function isRoadRoute(pathname: string): boolean {
  return ROAD_ROUTE_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

/** Pages that belong to the NUST FM newsroom (story-to-air). They do not exist in road-safety mode. */
export const NEWSROOM_ROUTE_PREFIXES = ["/stories", "/bulletins", "/studio", "/archive"] as const;

export function isNewsroomRoute(pathname: string): boolean {
  return NEWSROOM_ROUTE_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

/** Whether a page may be served in this mode: each product only serves its own pages. */
export function isRouteAllowed(pathname: string, mode: AppMode): boolean {
  return mode === "road_safety" ? !isNewsroomRoute(pathname) : !isRoadRoute(pathname);
}

export const PRODUCT_NAME = isNewsroomMode ? "NUST FM" : "SafeRouteZW";
