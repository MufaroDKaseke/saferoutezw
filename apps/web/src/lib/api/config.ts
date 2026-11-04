import type { DataMode } from "@/types";

/**
 * One switch for the whole app. `mock` runs every page on the labelled
 * synthetic dataset; `api` only talks to endpoints the backend really has.
 * Set with NEXT_PUBLIC_DATA_MODE (defaults to `mock`).
 */
export function getDataMode(): DataMode {
  return process.env.NEXT_PUBLIC_DATA_MODE === "api" ? "api" : "mock";
}

export const isMockMode = () => getDataMode() === "mock";

/**
 * Browser requests go to the app's own `/backend` path, which Next rewrites to
 * NEXT_PUBLIC_API_URL (see next.config.ts). The FastAPI app has no CORS config.
 */
export const API_BASE_PATH = "/backend";

export const MOCK_LATENCY_MS = (() => {
  const raw = Number(process.env.NEXT_PUBLIC_MOCK_LATENCY_MS);
  return Number.isFinite(raw) && raw >= 0 ? raw : 250;
})();

export const MAP_TILE_URL =
  process.env.NEXT_PUBLIC_MAP_TILE_URL ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
export const MAP_TILE_ATTRIBUTION =
  process.env.NEXT_PUBLIC_MAP_TILE_ATTRIBUTION ?? "&copy; OpenStreetMap contributors";
