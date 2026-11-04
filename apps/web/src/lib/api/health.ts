import { apiRequest } from "./client";
import { isMockMode } from "./config";
import type { HealthStatus } from "./types";

/**
 * The one endpoint the backend really serves. In mock mode this reports a
 * clearly-labelled demo status rather than pretending a backend answered.
 */
export async function getHealth(signal?: AbortSignal): Promise<HealthStatus & { demo: boolean }> {
  if (isMockMode()) {
    return { status: "demo", service: "mock data adapter", version: "n/a", demo: true };
  }
  const health = await apiRequest<HealthStatus>("GET /health", { signal });
  return { ...health, demo: false };
}
