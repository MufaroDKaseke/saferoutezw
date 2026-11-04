import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EndpointNotAvailableError } from "./errors";

/**
 * Mock mode and api mode must stay cleanly separated: in api mode nothing is
 * invented, and no request is ever sent to an endpoint the backend lacks.
 */
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
    const { listNews } = await import("./news");
    const { listIncidents } = await import("./incidents");
    const { approveIncident } = await import("./reviews");
    const { login } = await import("./auth");

    await expect(listNews({})).rejects.toBeInstanceOf(EndpointNotAvailableError);
    await expect(listIncidents({})).rejects.toBeInstanceOf(EndpointNotAvailableError);
    await expect(approveIncident("inc-0412", { headline: "h", body: "b" })).rejects.toBeInstanceOf(EndpointNotAvailableError);
    await expect(login({ email: "a@b.co", password: "x" })).rejects.toBeInstanceOf(EndpointNotAvailableError);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("names the missing endpoint so the UI can say exactly what is absent", async () => {
    const { listNews } = await import("./news");
    await expect(listNews({})).rejects.toMatchObject({ endpoint: "GET /api/v1/news" });
  });

  it("calls the one real endpoint, GET /health, through the same-origin proxy", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({ status: "ok", service: "saferoutezw-api", version: "0.1.0" }), { status: 200 }));
    const { getHealth } = await import("./health");
    const health = await getHealth();
    expect(health).toMatchObject({ status: "ok", demo: false });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(String(fetchSpy.mock.calls[0][0])).toBe("/backend/health");
  });

  it("turns a network failure into a readable error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    const { getHealth } = await import("./health");
    await expect(getHealth()).rejects.toThrow(/Could not reach the SafeRouteZW API/);
  });

  it("turns an HTTP error into an ApiError with its status", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "Service unavailable" }), { status: 503 }));
    const { getHealth } = await import("./health");
    await expect(getHealth()).rejects.toMatchObject({ name: "ApiError", status: 503 });
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
});
