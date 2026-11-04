import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EndpointNotAvailableError } from "./errors";

/**
 * Mock mode and api mode must stay cleanly separated: in api mode nothing is
 * invented, and no request is ever sent to an endpoint the backend lacks.
 */

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const bulletin = (n: number, headline = "Crash on A1", body = "Two people died.") => ({
  id: `b-${n}`,
  incident_id: "inc-1",
  version_number: n,
  headline,
  body,
  created_by: "u-1",
  created_by_name: "Test Editor",
  created_at: "2026-11-04T08:00:00Z",
  is_latest: true,
});

describe("api mode", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "api");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("refuses endpoints the backend does not have, without sending a request", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const { retryNewsProcessing } = await import("./news");
    const { listAlerts, publishAlert } = await import("./alerts");
    const { createSource } = await import("./sources");

    await expect(retryNewsProcessing("a-1")).rejects.toBeInstanceOf(EndpointNotAvailableError);
    await expect(listAlerts({})).rejects.toBeInstanceOf(EndpointNotAvailableError);
    await expect(publishAlert("al-1")).rejects.toBeInstanceOf(EndpointNotAvailableError);
    await expect(
      createSource({ name: "x", feedUrl: "https://x.test/feed", pollIntervalSeconds: 300, verificationTier: "unverified" }),
    ).rejects.toBeInstanceOf(EndpointNotAvailableError);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("names the missing endpoint so the UI can say exactly what is absent", async () => {
    const { listAlerts } = await import("./alerts");
    await expect(listAlerts({})).rejects.toMatchObject({ endpoint: "GET /api/v1/alerts" });
  });

  it("calls GET /health through the same-origin proxy", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(json({ status: "ok", service: "saferoutezw-api", version: "0.1.0" }));
    const { getHealth } = await import("./health");
    expect(await getHealth()).toMatchObject({ status: "ok", demo: false });
    expect(String(fetchSpy.mock.calls[0][0])).toBe("/backend/health");
  });

  it("turns a network failure into a readable error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    const { getHealth } = await import("./health");
    await expect(getHealth()).rejects.toThrow(/Could not reach the SafeRouteZW API/);
  });

  it("reads the API's error envelope and keeps its code", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json({ error: { code: "STALE_BULLETIN_VERSION", message: "A newer bulletin version exists." } }, 409),
    );
    const { getNewsItem } = await import("./news");
    await expect(getNewsItem("a-1")).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      code: "STALE_BULLETIN_VERSION",
      message: "A newer bulletin version exists.",
    });
  });

  it("names the field a validation error is about", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json({ error: { code: "VALIDATION_ERROR", message: "The request was not valid.", details: [{ field: "headline", message: "String should have at least 1 character" }] } }, 422),
    );
    const { getNewsItem } = await import("./news");
    await expect(getNewsItem("a-1")).rejects.toMatchObject({ status: 422, field: "headline" });
  });

  it("sends cookies, fills path parameters, and adds the CSRF token to writes only", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const path = String(url);
      if (path.endsWith("/auth/login")) {
        return json({ user: { id: "u-1", email: "e@x.test", display_name: "Ed", role: "editor", is_active: true, created_at: "2026-11-04T08:00:00Z" }, csrf_token: "csrf-123", expires_at: "2026-11-04T16:00:00Z" });
      }
      return json({});
    });
    const { login } = await import("./auth");
    const { apiRequest } = await import("./client");

    const result = await login({ email: "e@x.test", password: "pw" });
    expect(result.user).toMatchObject({ name: "Ed", role: "editor", isDemo: false });
    expect(result.simulated).toBe(false);

    await apiRequest("GET /api/v1/news/{id}", { params: { id: "a b" } });
    await apiRequest("POST /api/v1/incidents/{id}/bulletins", { params: { id: "inc-1" }, body: { headline: "h", body: "b", base_version: null } });

    const [, getInit] = fetchSpy.mock.calls[1];
    const [postUrl, postInit] = fetchSpy.mock.calls[2];
    expect(String(fetchSpy.mock.calls[1][0])).toBe("/backend/api/v1/news/a%20b");
    expect(getInit).toMatchObject({ method: "GET", credentials: "same-origin" });
    expect((getInit?.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
    expect(String(postUrl)).toBe("/backend/api/v1/incidents/inc-1/bulletins");
    expect((postInit?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-123");
  });

  it("tells listeners when the session is gone", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ error: { code: "UNAUTHENTICATED", message: "Sign in to continue." } }, 401));
    const { apiRequest, onUnauthenticated } = await import("./client");
    const listener = vi.fn();
    const off = onUnauthenticated(listener);
    await expect(apiRequest("GET /api/v1/incidents")).rejects.toMatchObject({ status: 401 });
    expect(listener).toHaveBeenCalledTimes(1);
    off();
  });

  it("maps API list responses onto the view types without inventing data", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json({
        items: [
          {
            id: "n-1", source_id: "s-1", publisher: "The Herald", source_kind: "rss", headline: "Kombi overturns near Rusape",
            source_url: "https://example.test/a", published_at: "2026-11-03T06:00:00Z", ingested_at: "2026-11-03T06:03:00Z",
            keyword_relevance: { relevant: true, reason: "matched: kombi, overturned" }, fetch_status: "ok",
            processing_status: "processed", extraction_status: "succeeded", linked_incident_count: 1,
          },
        ],
        total: 41, page: 2, page_size: 20,
      }),
    );
    const { listNews } = await import("./news");
    const page = await listNews({ page: 2 });
    expect(page).toMatchObject({ total: 41, page: 2, pageSize: 20 });
    const item = page.items[0];
    expect(item).toMatchObject({ publisherName: "The Herald", titleRedacted: "Kombi overturns near Rusape", workflowState: "processed", extractionStatus: "succeeded", synthetic: false });
    expect(item.screening).toMatchObject({ decision: "relevant", score: null });
    expect(item.screening?.matchedKeywords.map((k) => k.term)).toEqual(["kombi", "overturned"]);
  });

  it("saves a new bulletin version before approving it, with the version id and no reviewer", async () => {
    const calls: { url: string; method: string; body: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ url: String(url), method, body });
      if (method === "GET") return json({ items: [bulletin(1, "Old headline", "Old body")], total: 1, page: 1, page_size: 1 });
      if (String(url).endsWith("/bulletins")) return json(bulletin(2, "New headline", "New body"), 201);
      return json({ review: {}, incident: {} }, 201);
    });
    const { approveIncident } = await import("./reviews");
    const result = await approveIncident("inc-1", { headline: "New headline", body: "New body", notes: "Verified" });

    expect(result).toMatchObject({ simulated: false, data: { alertId: null, versionNumber: 2 } });
    const save = calls.find((c) => c.method === "POST" && c.url.endsWith("/bulletins"));
    expect(save?.body).toEqual({ headline: "New headline", body: "New body", base_version: 1 });
    const review = calls.find((c) => c.url.endsWith("/reviews"));
    expect(review?.body).toEqual({ decision: "approved", bulletin_version_id: "b-2", notes: "Verified" });
    expect(JSON.stringify(calls)).not.toContain("reviewer");
  });

  it("does not create a new version when the text has not changed", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
      calls.push(`${init?.method ?? "GET"} ${String(url)}`);
      if ((init?.method ?? "GET") === "GET") return json({ items: [bulletin(3, "Same", "Text")], total: 1, page: 1, page_size: 1 });
      return json({ review: {}, incident: {} }, 201);
    });
    const { approveIncident } = await import("./reviews");
    const result = await approveIncident("inc-1", { headline: "Same", body: "Text" });
    expect(result.data?.versionNumber).toBe(3);
    expect(calls.filter((c) => c.includes("/bulletins") && c.startsWith("POST"))).toHaveLength(0);
  });

  it("does not fall back to demo data when a request fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ error: { code: "DATABASE_ERROR", message: "The database is temporarily unavailable." } }, 503));
    const { listIncidents } = await import("./incidents");
    await expect(listIncidents({})).rejects.toMatchObject({ status: 503, code: "DATABASE_ERROR" });
  });
});

describe("mock mode", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "mock");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("serves the labelled demo dataset and never touches the network", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const { listNews } = await import("./news");
    const { getHealth } = await import("./health");
    const page = await listNews({ pageSize: 3 });
    expect(page.items).toHaveLength(3);
    expect(page.items.every((a) => a.synthetic)).toBe(true);
    expect(await getHealth()).toMatchObject({ demo: true });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("marks every simulated action as simulated", async () => {
    const { retryDelivery } = await import("./alerts");
    const { resetMockDb } = await import("@/lib/mock/store");
    resetMockDb();
    const result = await retryDelivery("alert-a0407", "sms");
    expect(result.simulated).toBe(true);
  });

  it("opens a labelled demo session without checking credentials", async () => {
    const { login } = await import("./auth");
    const result = await login({ email: "anyone@example.test", password: "x" });
    expect(result).toMatchObject({ simulated: true, user: { isDemo: true } });
  });
});
