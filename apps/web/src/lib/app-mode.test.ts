import { describe, expect, it } from "vitest";
import { ROAD_ROUTE_PREFIXES, isRoadRoute, isRouteAllowed, parseAppMode } from "./app-mode";

describe("parseAppMode", () => {
  it("defaults to road safety", () => {
    expect(parseAppMode(undefined)).toBe("road_safety");
    expect(parseAppMode("")).toBe("road_safety");
    expect(parseAppMode("something-else")).toBe("road_safety");
  });

  it("recognises the newsroom, ignoring spaces", () => {
    expect(parseAppMode("nust_newsroom")).toBe("nust_newsroom");
    expect(parseAppMode(" nust_newsroom ")).toBe("nust_newsroom");
  });
});

describe("isRouteAllowed", () => {
  it("allows every page in road-safety mode", () => {
    for (const prefix of ROAD_ROUTE_PREFIXES) expect(isRouteAllowed(prefix, "road_safety")).toBe(true);
    expect(isRouteAllowed("/news", "road_safety")).toBe(true);
  });

  it.each(["/map", "/incidents", "/incidents/123", "/blackspots", "/alerts/9", "/reviews", "/reviews/1", "/intelligence/statistics", "/public", "/public/routes", "/public/alerts/1"])(
    "blocks %s in newsroom mode",
    (path) => {
      expect(isRouteAllowed(path, "nust_newsroom")).toBe(false);
    },
  );

  it.each(["/dashboard", "/news", "/news/123", "/sources", "/processing", "/settings", "/login"])("allows %s in newsroom mode", (path) => {
    expect(isRouteAllowed(path, "nust_newsroom")).toBe(true);
  });

  it("matches whole path segments only", () => {
    expect(isRoadRoute("/mapping")).toBe(false);
    expect(isRoadRoute("/publications")).toBe(false);
    expect(isRoadRoute("/news/incidents")).toBe(false);
  });
});
