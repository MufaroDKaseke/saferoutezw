import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AlertCard } from "@/components/public/alert-card";
import { SeverityBadge } from "@/components/public/hazard";
import { HAZARD_LABELS, type PublicAlertSummary } from "@/lib/public-api/client";
import { GLYPHS, HAZARD_GLYPH, SEVERITY, markerHtml, severityStyle } from "@/lib/public-api/hazard-style";

const alert = (over: Partial<PublicAlertSummary> = {}): PublicAlertSummary => ({
  id: "11111111-1111-4111-8111-111111111111",
  headline: "Collision on the A3 near Rusape",
  summary: "Police are at the scene.",
  hazard_type: "collision",
  severity: "serious",
  location: "A3, Manicaland",
  province: "Manicaland",
  road_name: "A3",
  has_map_location: true,
  published_at: "2026-11-04T08:00:00Z",
  updated_at: "2026-11-04T08:30:00Z",
  sources: [{ name: "Example News", url: null }],
  ...over,
});

describe("hazard style data", () => {
  it("gives every hazard type a drawable icon", () => {
    for (const type of Object.keys(HAZARD_LABELS)) {
      expect(HAZARD_GLYPH[type], type).toBeDefined();
      expect(GLYPHS[HAZARD_GLYPH[type]]).toContain("<");
    }
  });

  it("falls back to 'not rated' for an unrecognised severity instead of guessing", () => {
    expect(severityStyle("catastrophic")).toBe(SEVERITY.unknown);
  });

  it("encodes category in marker shape and keeps blackspots dashed", () => {
    expect(markerHtml("alert", "road_closure", "serious")).toContain("<polygon");
    expect(markerHtml("alert", "traffic_disruption", "minor")).toContain("rotate(45)");
    expect(markerHtml("blackspot", "blackspot", "unknown")).toContain("stroke-dasharray");
    expect(markerHtml("alert", "collision", "fatal")).toContain(SEVERITY.fatal.marker.fill);
  });
});

describe("SeverityBadge", () => {
  it("always shows the severity as a word, not only a colour", () => {
    render(<SeverityBadge severity="fatal" />);
    expect(screen.getByText("Fatal")).toBeInTheDocument();
  });
});

describe("AlertCard", () => {
  it("shows hazard, severity, headline link, place and source", () => {
    render(<AlertCard alert={alert()} />);
    expect(screen.getByRole("link", { name: "Collision on the A3 near Rusape" })).toHaveAttribute(
      "href",
      "/public/alerts/11111111-1111-4111-8111-111111111111",
    );
    expect(screen.getByText("Serious")).toBeInTheDocument();
    expect(screen.getByText("Collision")).toBeInTheDocument();
    expect(screen.getByText("A3, Manicaland")).toBeInTheDocument();
    expect(screen.getByText("Example News")).toBeInTheDocument();
  });

  it("does not invent a severity badge when the editor has not rated the notice", () => {
    render(<AlertCard alert={alert({ severity: "unknown" })} />);
    expect(screen.queryByText("Not rated")).not.toBeInTheDocument();
    expect(screen.queryByText("Serious")).not.toBeInTheDocument();
  });
});
