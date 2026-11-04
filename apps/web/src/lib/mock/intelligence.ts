/**
 * Synthetic transport-intelligence data for demo mode. Everything here is invented and labelled
 * "[SYNTHETIC]"; none of the figures are real road-safety statistics.
 */
import type { components } from "@/lib/api/schema";
import { CATEGORY_LABELS, PRIMARY_CATEGORIES, SUBTYPES } from "@/lib/taxonomy.generated";

type S = components["schemas"];

const CREATED = "2026-11-03T08:00:00Z";

function record(
  n: number,
  fields: Partial<S["IntelligenceSummary"]> &
    Pick<S["IntelligenceSummary"], "headline" | "summary" | "primary_category" | "record_kind" | "geographic_scope">,
): S["IntelligenceSummary"] {
  return {
    id: `00000000-0000-4000-8000-0000000000${String(n).padStart(2, "0")}`,
    source_item_id: `10000000-0000-4000-8000-0000000000${String(n).padStart(2, "0")}`,
    primary_subtype: null,
    secondary_categories: [],
    temporal_status: "unknown",
    classification_confidence: 0.82,
    status: "candidate",
    event_date: null,
    province: null,
    district_or_town: null,
    road_name: null,
    publisher: "[SYNTHETIC] Example Daily",
    source_url: null,
    source_published_at: CREATED,
    incident_id: null,
    needs_editorial_review: true,
    topic_key: null,
    published_outputs: [],
    created_at: CREATED,
    ...fields,
  } as S["IntelligenceSummary"];
}

export const MOCK_RECORDS: S["IntelligenceSummary"][] = [
  record(1, {
    headline: "[SYNTHETIC] ZINARA announces road rehabilitation",
    summary: "[SYNTHETIC] A rehabilitation project was announced for a main road corridor. No closure is stated.",
    primary_category: "road_infrastructure", primary_subtype: "road_rehabilitation",
    record_kind: "informational_development", geographic_scope: "corridor", temporal_status: "planned",
    road_name: "Example corridor", topic_key: "road_infrastructure:example-corridor",
  }),
  record(2, {
    headline: "[SYNTHETIC] Annual road accident statistics released",
    summary: "[SYNTHETIC] An official body published national figures for a reporting year.",
    primary_category: "road_safety_data", primary_subtype: "accident_statistics",
    record_kind: "statistical_report", geographic_scope: "national", temporal_status: "historical",
    status: "approved",
  }),
  record(3, {
    headline: "[SYNTHETIC] New toll tariffs announced",
    summary: "[SYNTHETIC] Government announced new toll tariffs from a stated date.",
    primary_category: "transport_policy", primary_subtype: "toll_fee_change",
    record_kind: "informational_development", geographic_scope: "national",
    status: "published", published_outputs: ["transport_news"],
  }),
  record(4, {
    headline: "[SYNTHETIC] Road closed for bridge repairs",
    summary: "[SYNTHETIC] A road will be closed on a stated day for bridge repairs.",
    primary_category: "traffic_disruption", primary_subtype: "road_closure",
    record_kind: "actionable_event", geographic_scope: "road_segment", temporal_status: "planned",
    status: "under_review", incident_id: "20000000-0000-4000-8000-000000000004", road_name: "Example road",
  }),
  record(5, {
    headline: "[SYNTHETIC] Road safety campaign launched",
    summary: "[SYNTHETIC] A safety council launched a public awareness campaign.",
    primary_category: "road_safety", primary_subtype: "road_safety_campaign",
    record_kind: "informational_development", geographic_scope: "national",
  }),
  record(6, {
    headline: "[SYNTHETIC] Public transport fares change",
    summary: "[SYNTHETIC] An operator announced revised fares from a stated date.",
    primary_category: "public_transport", primary_subtype: "fare_change",
    record_kind: "informational_development", geographic_scope: "town",
  }),
];

export interface MockIntelligenceQuery {
  page?: number;
  pageSize?: number;
  category?: string;
  recordKind?: string;
  status?: string;
  q?: string;
}

export function listIntelligenceMock(q: MockIntelligenceQuery): S["Page_IntelligenceSummary_"] {
  const term = q.q?.trim().toLowerCase();
  const items = MOCK_RECORDS.filter(
    (r) =>
      (!q.category || r.primary_category === q.category) &&
      (!q.recordKind || r.record_kind === q.recordKind) &&
      (!q.status || r.status === q.status) &&
      (!term || r.headline.toLowerCase().includes(term) || r.summary.toLowerCase().includes(term)),
  );
  const pageSize = q.pageSize ?? 20;
  const page = q.page ?? 1;
  return { items: items.slice((page - 1) * pageSize, page * pageSize), total: items.length, page, page_size: pageSize };
}

export function getIntelligenceMock(id: string): S["IntelligenceDetail"] {
  const r = MOCK_RECORDS.find((x) => x.id === id);
  if (!r) throw new Error("Record not found");
  return {
    ...r,
    location_description: null,
    country: "Zimbabwe",
    source_attribution: null,
    taxonomy_version: "demo",
    extraction_version: "demo",
    details: {},
    quality: { flags: [], missing_information: [], ai_candidate: true },
    citations: [{ source_name: r.publisher, source_kind: "rss", title: r.headline, url: null, published_at: CREATED }],
    observations: [],
    versions: [],
    reviews: [],
    outputs: [],
    allowed_outputs: ["transport_news", "journalism_briefing", "dashboard_source"],
  } as S["IntelligenceDetail"];
}

export function categoriesMock(): S["CategoriesOut"] {
  return {
    taxonomy_version: "demo",
    categories: PRIMARY_CATEGORIES.map((c) => {
      const rows = MOCK_RECORDS.filter((r) => r.primary_category === c);
      return {
        category: c,
        label: CATEGORY_LABELS[c],
        subtypes: [...SUBTYPES[c]],
        total: rows.length,
        awaiting_review: rows.filter((r) => r.status === "candidate" || r.status === "under_review").length,
        published: rows.filter((r) => r.status === "published").length,
      };
    }),
    record_kinds: [],
    temporal_statuses: [],
    geographic_scopes: [],
  };
}

export function overviewMock(): S["OverviewOut"] {
  const by = categoriesMock().categories;
  return {
    by_category: by,
    awaiting_review: by.reduce((n, c) => n + c.awaiting_review, 0),
    published_by_output: { transport_news: 1 },
    recent: MOCK_RECORDS.slice(0, 6),
    latest_statistics: [],
  };
}

export function statisticsMock(): S["StatisticsOut"] {
  return {
    series: [],
    note: "Demo mode has no statistical observations. Connect the API to see reported figures with their periods and sources.",
  };
}

export function trendsMock(): S["TrendsOut"] {
  return {
    basis: "demo data",
    months: 12,
    total: MOCK_RECORDS.length,
    points: [{ month: "2026-11", category: "transport_policy", count: 1 }],
    sufficient_data: false,
    caveat: "Synthetic demo records; not a trend.",
  };
}

export function insightsMock(): S["InsightsOut"] {
  return { topic_groups: [], corridors: [], new_statistics: [], caveat: "Demo mode has no related-coverage data." };
}
