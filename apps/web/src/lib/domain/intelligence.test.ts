import { describe, expect, it } from "vitest";
import {
  CATEGORY_FILTERS,
  CLASSIFICATION_STATUS_LABEL,
  GEOGRAPHIC_SCOPE_LABEL,
  OUTPUT_LABEL,
  RECORD_STATUS_LABEL,
  categoryLabel,
  formatFigure,
  formatPeriod,
  isActionableKind,
  subtypeLabel,
} from "./intelligence";
import {
  CATEGORY_LABELS,
  GEOGRAPHIC_SCOPES,
  PRIMARY_CATEGORIES,
  PUBLICATION_OUTPUTS,
  RECORD_KINDS,
  RECORD_KIND_LABELS,
  RECORD_STATUSES,
  SUBTYPES,
  SUBTYPE_LABELS,
} from "@/lib/taxonomy.generated";

describe("category filters", () => {
  it("offers All plus the nine main categories, in the agreed order and wording", () => {
    expect(CATEGORY_FILTERS.map((f) => f.label)).toEqual([
      "All",
      "Road Incidents",
      "Traffic",
      "Road Hazards",
      "Infrastructure",
      "Public Transport",
      "Freight and Logistics",
      "Road Safety",
      "Road Safety Data",
      "Transport Policy",
    ]);
  });

  it("only filters by categories that exist in the generated taxonomy", () => {
    const real = new Set<string>(PRIMARY_CATEGORIES);
    for (const f of CATEGORY_FILTERS) if (f.value !== "all") expect(real.has(f.value)).toBe(true);
  });
});

describe("taxonomy labels", () => {
  it("has a label for every category, record kind, scope, status and output", () => {
    for (const c of PRIMARY_CATEGORIES) expect(CATEGORY_LABELS[c]).toBeTruthy();
    for (const k of RECORD_KINDS) expect(RECORD_KIND_LABELS[k]).toBeTruthy();
    for (const s of GEOGRAPHIC_SCOPES) expect(GEOGRAPHIC_SCOPE_LABEL[s]).toBeTruthy();
    for (const s of RECORD_STATUSES) expect(RECORD_STATUS_LABEL[s]).toBeTruthy();
    for (const o of PUBLICATION_OUTPUTS) expect(OUTPUT_LABEL[o]).toBeTruthy();
    for (const s of Object.keys(CLASSIFICATION_STATUS_LABEL)) expect(CLASSIFICATION_STATUS_LABEL[s as keyof typeof CLASSIFICATION_STATUS_LABEL]).toBeTruthy();
  });

  it("labels every subtype of every category", () => {
    for (const c of PRIMARY_CATEGORIES) for (const s of SUBTYPES[c]) expect(SUBTYPE_LABELS[s]).toBeTruthy();
    expect(subtypeLabel("head_on_collision")).toBe("Head on collision");
    expect(subtypeLabel(null)).toBe("No subtype");
  });

  it("falls back to the raw value for something unknown rather than hiding it", () => {
    expect(categoryLabel("something_new")).toBe("something_new");
  });

  it("matches the specified counts of subtypes", () => {
    expect(PRIMARY_CATEGORIES).toHaveLength(11); // ten transport categories + city_news
    expect(SUBTYPES.road_incident).toHaveLength(11);
    expect(SUBTYPES.road_safety_data).toHaveLength(9);
    expect(SUBTYPES.city_news).toHaveLength(9);
  });
});

describe("record kind", () => {
  it("treats only actionable events as events", () => {
    expect(isActionableKind("actionable_event")).toBe(true);
    for (const k of ["statistical_report", "informational_development", "research_or_analysis", "advisory", "unknown", null]) {
      expect(isActionableKind(k)).toBe(false);
    }
  });
});

describe("figures and periods", () => {
  it("shows a calendar year as the year", () => {
    expect(formatPeriod("2025-01-01", "2025-12-31")).toBe("2025");
  });
  it("shows other periods in full and missing periods honestly", () => {
    expect(formatPeriod("2025-01-01", "2025-03-31")).toBe("1 Jan 2025 to 31 Mar 2025");
    expect(formatPeriod(null, null)).toBe("Period not stated");
  });
  it("formats numbers with their unit", () => {
    expect(formatFigure(1800, "persons")).toBe("1,800 persons");
    expect(formatFigure(12.5, "%")).toBe("12.5%");
  });
});
