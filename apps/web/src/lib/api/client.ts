import { delay } from "@/lib/mock/query-utils";
import { API_BASE_PATH, isMockMode, MOCK_LATENCY_MS } from "./config";
import { ApiError, EndpointNotAvailableError } from "./errors";

/**
 * Endpoints the FastAPI backend actually serves, as "METHOD /path".
 *
 * This is the single place that records what exists. Today the backend only has
 * GET /health; every other v1 route is a reserved stub. A call to anything not
 * listed here throws EndpointNotAvailableError *before* any request is made, so
 * the UI can never present a call to an imaginary endpoint as working.
 *
 * When the backend ships an endpoint, add it here and the matching domain
 * function (src/lib/api/*.ts) starts using the real response.
 */
export const IMPLEMENTED_ENDPOINTS: ReadonlySet<string> = new Set(["GET /health"]);

export interface RequestOptions {
  query?: object;
  body?: unknown;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: object): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return `${API_BASE_PATH}${path}${qs ? `?${qs}` : ""}`;
}

/** Call a real backend endpoint. Refuses endpoints the backend does not have. */
export async function apiRequest<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  if (!IMPLEMENTED_ENDPOINTS.has(endpoint)) throw new EndpointNotAvailableError(endpoint);
  const [method, path] = endpoint.split(" ");
  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method,
      headers: options.body ? { "Content-Type": "application/json", Accept: "application/json" } : { Accept: "application/json" },
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
      cache: "no-store",
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError("Could not reach the SafeRouteZW API. Check that the backend is running.", null);
  }
  if (!response.ok) {
    let detail: string | null = null;
    try {
      const data = (await response.json()) as { detail?: unknown };
      detail = typeof data.detail === "string" ? data.detail : null;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(detail ?? `The API returned ${response.status}.`, response.status, detail);
  }
  return (await response.json()) as T;
}

export interface RouteSpec<T> {
  /** "METHOD /path" of the real endpoint this call maps to. */
  endpoint: string;
  /** Used only in mock mode. */
  mock: () => T;
  query?: object;
  body?: unknown;
  signal?: AbortSignal;
}

/**
 * Mock mode: run the mock adapter after a short simulated delay.
 * API mode: call the real endpoint, or fail loudly if it does not exist yet.
 */
export function route<T>({ endpoint, mock, query, body, signal }: RouteSpec<T>): Promise<T> {
  if (isMockMode()) return delay(mock, MOCK_LATENCY_MS);
  return apiRequest<T>(endpoint, { query, body, signal });
}
