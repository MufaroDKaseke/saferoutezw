import { delay } from "@/lib/mock/query-utils";
import { API_BASE_PATH, isMockMode, MOCK_LATENCY_MS } from "./config";
import { ApiError, EndpointNotAvailableError } from "./errors";

/**
 * Endpoints the FastAPI backend actually serves, as "METHOD /path".
 *
 * This is the single place that records what exists. A call to anything not
 * listed here throws EndpointNotAvailableError *before* any request is made, so
 * the UI can never present a call to an imaginary endpoint as working.
 *
 * Path parameters stay as `{name}` here and are filled from `params`.
 */
export const IMPLEMENTED_ENDPOINTS: ReadonlySet<string> = new Set([
  "GET /health",
  // auth
  "POST /api/v1/auth/login",
  "POST /api/v1/auth/logout",
  "GET /api/v1/auth/me",
  // read API
  "GET /api/v1/dashboard/summary",
  "GET /api/v1/dashboard/activity",
  "GET /api/v1/dashboard/incidents-by-month",
  "GET /api/v1/news",
  "GET /api/v1/news/{id}",
  "GET /api/v1/sources",
  "GET /api/v1/sources/{id}/runs",
  "GET /api/v1/processing/runs",
  "GET /api/v1/incidents",
  "GET /api/v1/incidents/{id}",
  "GET /api/v1/incidents/{id}/evidence",
  "GET /api/v1/incidents/{id}/location",
  "GET /api/v1/incidents/{id}/blackspot-matches",
  "GET /api/v1/blackspots",
  "GET /api/v1/map",
  // editorial workflow
  "GET /api/v1/reviews/pending",
  "GET /api/v1/reviews/counts",
  "GET /api/v1/incidents/{id}/bulletins",
  "POST /api/v1/incidents/{id}/bulletins",
  "GET /api/v1/incidents/{id}/reviews",
  "POST /api/v1/incidents/{id}/reviews",
  "POST /api/v1/incidents/{id}/location/confirm",
  "POST /api/v1/incidents/{id}/summary",
  // alerts: approved incidents, one-click publication
  "GET /api/v1/alerts",
  "GET /api/v1/alerts/{id}",
  "POST /api/v1/alerts/{id}/publish",
  "POST /api/v1/alerts/{id}/unpublish",
  // transport intelligence: classified records, statistics, editorial review, separate publication
  "GET /api/v1/intelligence",
  "GET /api/v1/intelligence/{id}",
  "GET /api/v1/intelligence/categories",
  "GET /api/v1/intelligence/overview",
  "GET /api/v1/intelligence/statistics",
  "GET /api/v1/intelligence/trends",
  "GET /api/v1/intelligence/insights",
  "POST /api/v1/intelligence/{id}/versions",
  "POST /api/v1/intelligence/{id}/reviews",
  "POST /api/v1/intelligence/{id}/publish",
  "POST /api/v1/intelligence/outputs/{output_id}/withdraw",
  // NUST FM newsroom mode: collected articles, general news classification, review flag
  "GET /api/v1/newsroom/articles",
  "GET /api/v1/newsroom/articles/{id}",
  "GET /api/v1/newsroom/summary",
  "PATCH /api/v1/newsroom/articles/{id}/review",
  "POST /api/v1/newsroom/articles/{id}/retry",
  // NUST FM story-to-air: stories, script versions, approval
  "GET /api/v1/newsroom/assignees",
  "GET /api/v1/newsroom/stories",
  "POST /api/v1/newsroom/stories",
  "GET /api/v1/newsroom/stories/{id}",
  "PATCH /api/v1/newsroom/stories/{id}",
  "POST /api/v1/newsroom/stories/{id}/verify",
  "POST /api/v1/newsroom/stories/{id}/scripts",
  "POST /api/v1/newsroom/stories/{id}/scripts/draft",
  "POST /api/v1/newsroom/stories/{id}/submit",
  "POST /api/v1/newsroom/stories/{id}/review",
  "POST /api/v1/newsroom/stories/{id}/drop",
  // NUST FM radio bulletins: numbered revisions, one approved at a time
  "GET /api/v1/newsroom/bulletins",
  "POST /api/v1/newsroom/bulletins",
  "GET /api/v1/newsroom/bulletins/{id}",
  "GET /api/v1/newsroom/bulletins/{id}/studio",
  "POST /api/v1/newsroom/bulletins/{id}/revisions",
  "PUT /api/v1/newsroom/bulletins/{id}/revisions/{number}/items",
  "POST /api/v1/newsroom/bulletins/{id}/revisions/{number}/submit",
  "POST /api/v1/newsroom/bulletins/{id}/revisions/{number}/approve",
  "POST /api/v1/newsroom/bulletins/{id}/revisions/{number}/reject",
  "POST /api/v1/newsroom/bulletins/{id}/broadcast",
  // NUST FM archive: what went to air
  "GET /api/v1/newsroom/archive",
  "GET /api/v1/newsroom/archive/stories/{id}",
  "GET /api/v1/newsroom/archive/bulletins",
  "GET /api/v1/newsroom/archive/bulletins/{id}/revisions/{number}",
]);

export interface RequestOptions {
  query?: object;
  body?: unknown;
  /** Values for `{name}` placeholders in the endpoint path. */
  params?: Record<string, string>;
  signal?: AbortSignal;
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/* The CSRF token comes from login or /auth/me and lives only in memory. */
let csrfToken: string | null = null;
export const setCsrfToken = (token: string | null) => {
  csrfToken = token;
};

/** Called when the API says the session is gone, so the UI can send the user to /login. */
const unauthenticatedListeners = new Set<() => void>();
export function onUnauthenticated(listener: () => void): () => void {
  unauthenticatedListeners.add(listener);
  return () => unauthenticatedListeners.delete(listener);
}

function fillPath(path: string, params: Record<string, string> = {}): string {
  return path.replace(/\{(\w+)\}/g, (_, name: string) => {
    const value = params[name];
    if (value === undefined) throw new Error(`Missing path parameter "${name}" for ${path}`);
    return encodeURIComponent(value);
  });
}

function buildUrl(path: string, query?: object): string {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (Array.isArray(value)) {
      // A list becomes a repeated parameter (?stage=a&stage=b), which is what FastAPI expects.
      for (const item of value) if (item !== undefined && item !== null && item !== "") searchParams.append(key, String(item));
    } else if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, String(value));
    }
  }
  const qs = searchParams.toString();
  return `${API_BASE_PATH}${path}${qs ? `?${qs}` : ""}`;
}

interface ErrorEnvelope {
  error?: { code?: string; message?: string; details?: { field?: string; message?: string }[] };
  detail?: unknown;
}

/** Call a real backend endpoint. Refuses endpoints the backend does not have. */
export async function apiRequest<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  if (!IMPLEMENTED_ENDPOINTS.has(endpoint)) throw new EndpointNotAvailableError(endpoint);
  const [method, template] = endpoint.split(" ");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (!SAFE_METHODS.has(method) && csrfToken) headers["X-CSRF-Token"] = csrfToken;

  let response: Response;
  try {
    response = await fetch(buildUrl(fillPath(template, options.params), options.query), {
      method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
      cache: "no-store",
      credentials: "same-origin",
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError("Could not reach the SafeRouteZW API. Check that the backend is running.", null);
  }

  if (!response.ok) {
    let message: string | null = null;
    let code: string | null = null;
    let field: string | null = null;
    try {
      const data = (await response.json()) as ErrorEnvelope;
      message = data.error?.message ?? (typeof data.detail === "string" ? data.detail : null);
      code = data.error?.code ?? null;
      const first = data.error?.details?.[0];
      if (first?.message) {
        field = first.field ?? null;
        message = `${message ?? "The request was not valid."} ${first.message}`.trim();
      }
    } catch {
      /* response had no JSON body */
    }
    if (response.status === 401 && code === "UNAUTHENTICATED" && endpoint !== "GET /api/v1/auth/me") {
      csrfToken = null;
      unauthenticatedListeners.forEach((listener) => listener());
    }
    throw new ApiError(message ?? `The API returned ${response.status}.`, response.status, message, code, field);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface RouteSpec<T> {
  /** "METHOD /path" of the real endpoint this call maps to. */
  endpoint: string;
  /** Used only in mock mode. */
  mock: () => T;
  query?: object;
  body?: unknown;
  params?: Record<string, string>;
  signal?: AbortSignal;
}

/**
 * Mock mode: run the mock adapter after a short simulated delay.
 * API mode: call the real endpoint, or fail loudly if it does not exist yet.
 */
export function route<T>({ endpoint, mock, query, body, params, signal }: RouteSpec<T>): Promise<T> {
  if (isMockMode()) return delay(mock, MOCK_LATENCY_MS);
  return apiRequest<T>(endpoint, { query, body, params, signal });
}

/**
 * Like `route`, but for API calls that need several requests and a mapping step.
 * `live` runs only in api mode, `mock` only in mock mode. Nothing falls back silently.
 */
export function dual<T>({ mock, live }: { mock: () => T; live: () => Promise<T> }): Promise<T> {
  if (isMockMode()) return delay(mock, MOCK_LATENCY_MS);
  return live();
}
