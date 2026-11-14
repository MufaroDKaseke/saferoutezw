/**
 * Public API client. Separate from the internal newsroom client: it never uses the mock store, and
 * a failed request is an error the UI must show, never fabricated data.
 *
 * Server components call the API directly (API_INTERNAL_URL / NEXT_PUBLIC_API_URL); browsers go
 * through the same-origin `/backend` rewrite (see next.config.ts).
 */
import type { components } from "@/lib/api/schema";
import { DEFAULT_LOCALE, intlTag, type Locale } from "@/lib/i18n/config";
import type { Translator } from "@/lib/i18n/translate";
import { limitProvinces } from "@/lib/scope";

type S = components["schemas"];

export type PublicAlertSummary = S["PublicAlertSummary"];
export type PublicAlertDetail = S["PublicAlertDetail"];
export type PublicAlertPage = S["PublicAlertPage"];
export type PublicSummary = S["PublicSummary"];
export type PublicMapCollection = S["PublicMapCollection"];
export type PublicBlackspotList = S["PublicBlackspotList"];
export type PublicBlackspot = S["PublicBlackspot"];
export type RoutePlanRequest = S["RoutePlanRequest"];
export type RoutePlanResponse = S["RoutePlanResponse"];
export type RouteHazard = S["RouteHazard"];
export type PublicTransportItem = S["PublicTransportItem"];
export type PublicTransportPage = S["Page_PublicTransportItem_"];
export type PublicStatistics = S["PublicStatistics"];
export type SubscriptionOptions = S["OptionsOut"];
export type SubscriptionPreferences = S["PreferencesOut"];

const API_PREFIX = "/api/v1/public";

export class PublicApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
    this.name = "PublicApiError";
  }
}

function baseUrl(): string {
  if (typeof window === "undefined") {
    return process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  }
  return "/backend";
}

type Query = Record<string, string | number | undefined | null>;

async function request<T>(
  method: "GET" | "POST" | "PATCH",
  path: string,
  options: { query?: Query; body?: unknown; token?: string; signal?: AbortSignal } = {},
): Promise<T> {
  const url = new URL(`${baseUrl()}${API_PREFIX}${path}`, typeof window === "undefined" ? undefined : window.location.origin);
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      cache: "no-store",
      signal: options.signal,
    });
  } catch {
    throw new PublicApiError("SafeRouteZW could not be reached. Check your connection and try again.", 0, "NETWORK");
  }
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    let code = "ERROR";
    try {
      const data = await response.json();
      if (data?.error?.message) message = String(data.error.message);
      if (data?.error?.code) code = String(data.error.code);
    } catch {
      /* keep the generic message */
    }
    if (response.status === 429) message = "Too many requests. Please wait a moment and try again.";
    throw new PublicApiError(message, response.status, code);
  }
  return (await response.json()) as T;
}

export const publicApi = {
  summary: () => request<PublicSummary>("GET", "/summary"),
  alerts: (query: { page?: number; page_size?: number; q?: string; province?: string; road?: string; hazard_type?: string }) =>
    request<PublicAlertPage>("GET", "/alerts", { query }),
  alert: (id: string) => request<PublicAlertDetail>("GET", `/alerts/${encodeURIComponent(id)}`),
  map: (query: { hazard_type?: string; severity?: string; since_days?: number } = {}, signal?: AbortSignal) =>
    request<PublicMapCollection>("GET", "/map", { query, signal }),
  blackspots: (signal?: AbortSignal) => request<PublicBlackspotList>("GET", "/blackspots", { signal }),
  transportNews: (query: { page?: number; page_size?: number; category?: string } = {}) =>
    request<PublicTransportPage>("GET", "/transport/news", { query }),
  transportInsights: (query: { page?: number; page_size?: number } = {}) =>
    request<PublicTransportPage>("GET", "/transport/insights", { query }),
  transportStatistics: (query: { metric?: string; limit?: number } = {}) =>
    request<PublicStatistics>("GET", "/transport/statistics", { query }),
  planRoute: (body: RoutePlanRequest) => request<RoutePlanResponse>("POST", "/routes/plan", { body }),

  subscriptionOptions: () => request<SubscriptionOptions>("GET", "/subscriptions/options"),
  subscribe: (body: unknown) => request<S["AckOut"]>("POST", "/subscriptions", { body }),
  resendVerification: (body: { phone: string; country_code: string }) =>
    request<S["AckOut"]>("POST", "/subscriptions/resend-verification", { body }),
  verify: (body: { phone: string; country_code: string; code: string }) =>
    request<S["VerifyOut"]>("POST", "/subscriptions/verify", { body }),
  preferences: (token: string) => request<SubscriptionPreferences>("GET", "/subscriptions/preferences", { token }),
  updatePreferences: (token: string, body: { all_zimbabwe: boolean; provinces: string[]; corridors: string[] }) =>
    request<SubscriptionPreferences>("PATCH", "/subscriptions/preferences", { token, body }),
  unsubscribe: (token: string) => request<S["AckOut"]>("POST", "/subscriptions/unsubscribe", { token }),
};

/** Run a request and return the outcome as a value, so pages can render without JSX inside try/catch. */
export async function attempt<T>(run: () => Promise<T>): Promise<{ data: T; error: null } | { data: null; error: PublicApiError }> {
  try {
    return { data: await run(), error: null };
  } catch (e) {
    return {
      data: null,
      error: e instanceof PublicApiError ? e : new PublicApiError("Something went wrong. Please try again.", 0, "ERROR"),
    };
  }
}

export const HAZARD_LABELS: Record<string, string> = {
  collision: "Collision",
  pedestrian_strike: "Pedestrian incident",
  rollover: "Rollover",
  vehicle_fire: "Vehicle fire",
  breakdown: "Breakdown",
  road_hazard: "Road hazard",
  road_closure: "Road closure",
  traffic_disruption: "Traffic disruption",
  other: "Other",
};

const ALL_PROVINCES = [
  "Bulawayo",
  "Harare",
  "Manicaland",
  "Mashonaland Central",
  "Mashonaland East",
  "Mashonaland West",
  "Masvingo",
  "Matabeleland North",
  "Matabeleland South",
  "Midlands",
] as const;

/** All ten provinces, or the ones this deployment offers (NEXT_PUBLIC_PROVINCES). */
export const PROVINCES: readonly (typeof ALL_PROVINCES)[number][] = limitProvinces(ALL_PROVINCES);

export function formatKm(meters: number): string {
  return `${(meters / 1000).toFixed(meters >= 100_000 ? 0 : 1)} km`;
}

/** "1 h 5 min". Pass the translator to get the unit words in the reader's language. */
export function formatDuration(seconds: number, t?: Translator["t"]): string {
  const min = t ? t("unit.min") : "min";
  const hour = t ? t("unit.hour") : "h";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} ${min}`;
  return `${Math.floor(minutes / 60)} ${hour} ${minutes % 60} ${min}`;
}

export function formatWhen(iso: string, locale: Locale = DEFAULT_LOCALE): string {
  return new Date(iso).toLocaleString(intlTag(locale), { dateStyle: "medium", timeStyle: "short", timeZone: "Africa/Harare" });
}

/**
 * Wording for an error. Messages the app wrote itself are shown in the reader's language; wording that
 * came from the API (for example a specific validation message) is shown exactly as the API sent it.
 */
export function describeError(error: unknown, t: Translator["t"]): string {
  if (error instanceof PublicApiError) {
    if (error.code === "NETWORK") return t("error.network");
    if (error.status === 429) return t("error.rateLimited");
    if (error.code === "ERROR") return t("error.generic");
    return error.message;
  }
  return t("error.generic");
}
