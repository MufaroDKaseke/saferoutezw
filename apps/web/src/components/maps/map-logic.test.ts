import { describe, expect, it } from "vitest";
import { clusterPoints, markerKind, project } from "./map-logic";

describe("markerKind keeps the four meanings apart", () => {
  const none = new Set<string>();
  it("an incident with an alert is approved, even if its status lags", () => {
    expect(markerKind({ id: "a", reviewState: "pending" }, new Set(["a"]))).toBe("approved");
  });
  it("approved review state is approved", () => {
    expect(markerKind({ id: "a", reviewState: "approved" }, none)).toBe("approved");
  });
  it("needs_changes is reviewed but not approved", () => {
    expect(markerKind({ id: "a", reviewState: "needs_changes" }, none)).toBe("reviewed");
  });
  it("everything else is an unverified report", () => {
    expect(markerKind({ id: "a", reviewState: "pending" }, none)).toBe("reported");
  });
});

describe("clusterPoints", () => {
  const harare = { id: "h1", lat: -17.83, lng: 31.05 };
  const nearHarare = { id: "h2", lat: -17.84, lng: 31.06 };
  const bulawayo = { id: "b1", lat: -20.15, lng: 28.58 };

  it("groups nearby points at a wide zoom", () => {
    const clusters = clusterPoints([harare, nearHarare, bulawayo], 6);
    expect(clusters).toHaveLength(2);
    expect(clusters.find((c) => c.members.length === 2)?.members.map((m) => m.id).sort()).toEqual(["h1", "h2"]);
  });

  it("separates the same points when zoomed in", () => {
    expect(clusterPoints([harare, nearHarare, bulawayo], 14)).toHaveLength(3);
  });

  it("keeps a single point as itself", () => {
    const [only] = clusterPoints([bulawayo], 6);
    expect(only.key).toBe("b1");
    expect(only.members).toEqual([bulawayo]);
  });

  it("places a cluster at the mean position of its members", () => {
    const cluster = clusterPoints([harare, nearHarare], 6)[0];
    expect(cluster.lat).toBeCloseTo((harare.lat + nearHarare.lat) / 2, 6);
    expect(cluster.lng).toBeCloseTo((harare.lng + nearHarare.lng) / 2, 6);
  });
});

describe("project", () => {
  it("doubles pixel distance for each zoom level", () => {
    const a = project(-18, 30, 5);
    const b = project(-18, 30, 6);
    expect(b.x).toBeCloseTo(a.x * 2, 3);
    expect(b.y).toBeCloseTo(a.y * 2, 3);
  });
});
