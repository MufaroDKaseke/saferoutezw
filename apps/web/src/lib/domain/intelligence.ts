import {
  CATEGORY_LABELS,
  RECORD_KIND_LABELS,
  SUBTYPE_LABELS,
  type GeographicScope,
  type PrimaryCategory,
  type PublicationOutputType,
  type RecordKind,
  type RecordStatus,
} from "@/lib/taxonomy.generated";
import type { ClassificationStatus } from "@/types";

/**
 * News Monitor / Intelligence category filters. Short everyday names for the editors' chips;
 * every value is a PrimaryCategory from the generated taxonomy, never a free string.
 */
export const CATEGORY_FILTERS: readonly { value: "all" | PrimaryCategory; label: string }[] = [
  { value: "all", label: "All" },
  { value: "road_incident", label: "Road Incidents" },
  { value: "traffic_disruption", label: "Traffic" },
  { value: "road_hazard", label: "Road Hazards" },
  { value: "road_infrastructure", label: "Infrastructure" },
  { value: "public_transport", label: "Public Transport" },
  { value: "freight_and_logistics", label: "Freight and Logistics" },
  { value: "road_safety", label: "Road Safety" },
  { value: "road_safety_data", label: "Road Safety Data" },
  { value: "transport_policy", label: "Transport Policy" },
];

export const categoryLabel = (c: PrimaryCategory | string): string =>
  (CATEGORY_LABELS as Record<string, string>)[c] ?? c;
export const recordKindLabel = (k: RecordKind | string): string =>
  (RECORD_KIND_LABELS as Record<string, string>)[k] ?? k;
export const subtypeLabel = (s: string | null | undefined): string => (s ? (SUBTYPE_LABELS[s] ?? s) : "No subtype");

export const CLASSIFICATION_STATUS_LABEL: Record<ClassificationStatus, string> = {
  unscreened: "Not screened yet",
  filtered: "Filtered out",
  awaiting_classification: "Awaiting AI classification",
  classified: "Classified",
  not_relevant: "Not transport-relevant",
  failed: "Processing failed",
};

export const GEOGRAPHIC_SCOPE_LABEL: Record<GeographicScope, string> = {
  precise_point: "Precise point",
  approximate_point: "Approximate point",
  road_segment: "Road segment",
  corridor: "Road corridor",
  town: "Town",
  district: "District",
  province: "Province",
  national: "National",
  regional: "Regional",
  unknown: "Unknown",
};

export const RECORD_STATUS_LABEL: Record<RecordStatus, string> = {
  candidate: "Candidate",
  under_review: "Under review",
  approved: "Approved",
  rejected: "Rejected",
  published: "Published",
  archived: "Archived",
};

export const OUTPUT_LABEL: Record<PublicationOutputType, string> = {
  transport_news: "Transport news item",
  statistical_insight: "Statistical insight",
  analytical_report: "Analytical report",
  journalism_briefing: "Journalism briefing",
  dashboard_source: "Dashboard data source",
};

export const geographicScopeLabel = (s: string | null | undefined): string =>
  s ? ((GEOGRAPHIC_SCOPE_LABEL as Record<string, string>)[s] ?? s) : "Not set";

/** Only these kinds describe a specific occurrence that could affect a journey. */
export const isActionableKind = (k: string | null | undefined): boolean => k === "actionable_event";

/** "2025" for a calendar year, "1 Jan 2025 to 31 Mar 2025" otherwise, "Period not stated" when unknown. */
export function formatPeriod(start: string | null | undefined, end: string | null | undefined): string {
  if (!start && !end) return "Period not stated";
  const fmt = (iso: string) =>
    new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  if (start && end) {
    if (start.endsWith("-01-01") && end.endsWith("-12-31") && start.slice(0, 4) === end.slice(0, 4)) return start.slice(0, 4);
    return start === end ? fmt(start) : `${fmt(start)} to ${fmt(end)}`;
  }
  return fmt((start ?? end) as string);
}

export function formatFigure(value: number, unit: string): string {
  const n = Number.isInteger(value) ? value.toLocaleString("en-GB") : value.toLocaleString("en-GB", { maximumFractionDigits: 2 });
  return unit === "%" ? `${n}%` : `${n} ${unit}`;
}
