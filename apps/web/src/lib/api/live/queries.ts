/**
 * API-mode implementations of the read calls. Each one calls real endpoints and maps the
 * response onto the existing view types. Nothing here falls back to mock data: if the
 * API fails, the error reaches the screen.
 */
import type {
  ArticleWorkflowState,
  AuditEvent,
  Blackspot,
  DashboardRange,
  DashboardSummary,
  Incident,
  IncidentDetail,
  Paginated,
  ProcessingBacklog,
  ProcessingJob,
  ReviewQueueItem,
  ReviewState,
  ReviewWorkspace,
  SourceItem,
  SourceItemDetail,
  SourceSummary,
  IngestionRun,
} from "@/types";
import { apiRequest } from "../client";
import type { components } from "../schema";
import type {
  BlackspotQuery,
  DateRangeKey,
  IncidentQuery,
  MapQuery,
  NewsQuery,
  PageQuery,
  ProcessingQuery,
  ReviewQuery,
} from "../types";
import {
  mapIncidentToIncident,
  toBlackspot,
  toBulletin,
  toExtractedEvent,
  toIncident,
  toIncidentDetail,
  toIngestionRun,
  toPaginated,
  toProcessingJob,
  toReview,
  toReviewQueueItem,
  toSourceItem,
  toSourceItemDetail,
  toSourceSummary,
} from "./mappers";

type S = components["schemas"];
type Page<T> = { items: T[]; total: number; page: number; page_size: number };

const RANGE_MS: Record<Exclude<DateRangeKey, "all">, number> = {
  "24h": 24 * 3600_000,
  "7d": 7 * 24 * 3600_000,
  "30d": 30 * 24 * 3600_000,
};

const since = (range?: DateRangeKey) =>
  range && range !== "all" ? new Date(Date.now() - RANGE_MS[range]).toISOString() : undefined;

function paging(q: PageQuery) {
  return { page: q.page, page_size: q.pageSize, order: q.dir };
}

const SORT_KEYS: Record<string, string> = {
  receivedAt: "received_at",
  publishedAt: "published_at",
  createdAt: "created_at",
  updatedAt: "created_at",
  occurredAt: "occurred_at",
  credibilityScore: "credibility_score",
  credibility: "credibility_score",
  geographicRiskScore: "geographic_risk_score",
};
const sortKey = (sort: string | undefined, allowed: string[]) => {
  const mapped = sort ? (SORT_KEYS[sort] ?? sort) : undefined;
  return mapped && allowed.includes(mapped) ? mapped : undefined;
};

/* --------------------------------------------------------------------- news */

const STATUS_FOR_WORKFLOW: Partial<Record<ArticleWorkflowState, string>> = {
  new: "pending",
  filtered: "filtered",
  relevant: "screened",
  awaiting_full_text: "screened",
  full_text_retrieved: "fetched",
  extraction_pending: "fetched",
  processed: "processed",
  failed: "failed",
};

export async function listNewsLive(q: NewsQuery): Promise<Paginated<SourceItem>> {
  const page = await apiRequest<Page<S["NewsItemSummary"]>>("GET /api/v1/news", {
    query: {
      ...paging(q),
      q: q.search || q.keyword,
      source_id: q.publisherId,
      relevant: q.relevance === "relevant" ? true : q.relevance === "not_relevant" ? false : undefined,
      processing_status: q.status ? STATUS_FOR_WORKFLOW[q.status] : undefined,
      category: q.category,
      record_kind: q.recordKind,
      received_from: since(q.range),
      sort: sortKey(q.sort, ["received_at", "published_at"]),
    },
  });
  // The list reports only how many incidents an article feeds; the ids are on the detail.
  return toPaginated(page, (item) =>
    toSourceItem(item, Array.from({ length: item.linked_incident_count }, (_, n) => `${item.id}#${n}`)),
  );
}

export async function getNewsLive(id: string): Promise<SourceItemDetail> {
  return toSourceItemDetail(await apiRequest<S["NewsItemDetail"]>("GET /api/v1/news/{id}", { params: { id } }));
}

/* ------------------------------------------------------------------ sources */

export async function listSourcesLive(): Promise<SourceSummary[]> {
  const page = await apiRequest<Page<S["SourceOut"]>>("GET /api/v1/sources", { query: { page_size: 100 } });
  return page.items.map(toSourceSummary);
}

export async function listIngestionHistoryLive(sourceId: string): Promise<IngestionRun[]> {
  const page = await apiRequest<Page<S["IngestionRunOut"]>>("GET /api/v1/sources/{id}/runs", {
    params: { id: sourceId },
    query: { page_size: 50 },
  });
  return page.items.map(toIngestionRun);
}

/* --------------------------------------------------------------- processing */

export async function listProcessingLive(q: ProcessingQuery): Promise<Paginated<ProcessingJob>> {
  // Only two kinds are recorded as runs; screening and retrieval are item states, not runs.
  if (q.kind === "keyword_screening" || q.kind === "article_retrieval") {
    return { items: [], total: 0, page: q.page ?? 1, pageSize: q.pageSize ?? 20 };
  }
  const page = await apiRequest<Page<S["ProcessingRun"]>>("GET /api/v1/processing/runs", {
    query: {
      ...paging(q),
      kind: q.kind === "rss_poll" ? "ingestion" : q.kind === "ai_extraction" ? "extraction" : undefined,
      status: q.status,
      source_id: q.sourceId,
      started_from: since(q.range),
    },
  });
  return toPaginated(page, toProcessingJob);
}

export async function getBacklogLive(): Promise<ProcessingBacklog> {
  const summary = await apiRequest<S["DashboardSummary"]>("GET /api/v1/dashboard/summary", { query: { range: "24h" } });
  const p = summary.pipeline;
  return {
    awaitingScreening: p.pending ?? 0,
    awaitingFullText: p.screened ?? 0,
    awaitingExtraction: p.fetched ?? 0,
    failedNeedingAttention: (p.failed ?? 0) + (p.fetch_failed ?? 0),
  };
}

/* ---------------------------------------------------------------- incidents */

export async function listIncidentsLive(q: IncidentQuery): Promise<Paginated<Incident>> {
  const status =
    q.reviewState === "approved" ? "approved" : q.reviewState === "rejected" ? "rejected" : undefined;
  const page = await apiRequest<Page<S["IncidentSummary"]>>("GET /api/v1/incidents", {
    query: {
      ...paging(q),
      q: q.search,
      status,
      incident_type: q.type,
      severity: q.severity,
      created_from: since(q.range),
      sort: sortKey(q.sort, ["created_at", "occurred_at", "credibility_score", "geographic_risk_score"]),
    },
  });
  let result = toPaginated(page, (i) => toIncident(i));
  if (q.reviewState === "pending" || q.reviewState === "needs_changes") {
    // The API has no review-state filter; filter the loaded page (totals are for the page's source query).
    result = { ...result, items: result.items.filter((i) => i.reviewState === q.reviewState) };
  }
  if (q.verification) result = { ...result, items: result.items.filter((i) => i.verification === q.verification) };
  return result;
}

export async function getIncidentLive(id: string): Promise<{ incident: IncidentDetail; history: AuditEvent[] }> {
  const [detail, evidence, matches] = await Promise.all([
    apiRequest<S["IncidentDetail"]>("GET /api/v1/incidents/{id}", { params: { id } }),
    apiRequest<Page<S["EvidenceOut"]>>("GET /api/v1/incidents/{id}/evidence", { params: { id }, query: { page_size: 100 } }),
    apiRequest<S["BlackspotMatchesOut"]>("GET /api/v1/incidents/{id}/blackspot-matches", { params: { id } }),
  ]);
  // The audit trail has no read endpoint yet, so the history is honestly empty.
  return { incident: toIncidentDetail(detail, evidence.items, matches), history: [] };
}

/* --------------------------------------------------------------- map/blackspots */

export interface LiveMapData {
  incidents: Incident[];
  alertIncidentIds: string[];
  blackspots: Blackspot[];
}

export async function getMapDataLive(q: MapQuery): Promise<LiveMapData> {
  const data = await apiRequest<S["MapData"]>("GET /api/v1/map");
  const from = q.range && q.range !== "all" ? Date.now() - RANGE_MS[q.range] : null;
  const term = q.search?.trim().toLowerCase();
  const incidents = data.incidents
    .map(mapIncidentToIncident)
    .filter((i) => !q.severity || i.severity === q.severity)
    .filter((i) => from === null || (i.occurredAt !== null && new Date(i.occurredAt).getTime() >= from))
    .filter((i) => !term || `${i.referenceCode} ${i.locationText ?? ""}`.toLowerCase().includes(term));
  return {
    incidents,
    // Approved incidents stand where public alerts will be shown once distribution exists.
    alertIncidentIds: data.incidents.filter((m) => m.marker_kind === "approved").map((m) => m.id),
    blackspots: data.blackspots.map(toBlackspot),
  };
}

export async function listBlackspotsLive(q: BlackspotQuery): Promise<Paginated<Blackspot>> {
  const page = await apiRequest<Page<S["BlackspotOut"]>>("GET /api/v1/blackspots", {
    query: { ...paging(q), q: q.search, risk_level: q.risk },
  });
  return toPaginated(page, toBlackspot);
}

/* ---------------------------------------------------------------- dashboard */

export async function getDashboardLive(range: DashboardRange): Promise<DashboardSummary> {
  const [summary, activity, news, pending, sources, map] = await Promise.all([
    apiRequest<S["DashboardSummary"]>("GET /api/v1/dashboard/summary", { query: { range } }),
    apiRequest<S["DashboardActivity"]>("GET /api/v1/dashboard/activity", { query: { range } }),
    apiRequest<Page<S["NewsItemSummary"]>>("GET /api/v1/news", { query: { page_size: 5, has_incident: true } }),
    apiRequest<Page<S["IncidentSummary"]>>("GET /api/v1/reviews/pending", { query: { page_size: 5 } }),
    apiRequest<Page<S["SourceOut"]>>("GET /api/v1/sources", { query: { page_size: 100 } }),
    apiRequest<S["MapData"]>("GET /api/v1/map", { query: { include_blackspots: false } }),
  ]);
  const p = summary.pipeline;
  const oldest = summary.oldest_pending_at
    ? Math.floor((Date.now() - new Date(summary.oldest_pending_at).getTime()) / 86_400_000)
    : null;
  return {
    range,
    asOf: summary.until,
    kpis: {
      articlesIngested: summary.articles_ingested,
      roadRelevantArticles: summary.relevant_articles,
      incidentCandidates: summary.incident_candidates,
      pendingReviews: summary.pending_reviews,
      highPriorityPending: summary.high_priority_pending,
      oldestPendingDays: oldest,
      approvedAlerts: summary.approved_incidents,
      failedJobs: summary.failed_processing,
    },
    pipeline: {
      ingested: summary.articles_ingested,
      aiExtracted: (p.processed ?? 0) + (p.discarded ?? 0),
      awaitingDecision: summary.pending_reviews,
      approvedByEditor: summary.approved_incidents,
      fullyShared: 0, // public distribution is not built yet
    },
    activity: activity.points.map((pt) => ({
      date: pt.bucket_start,
      articles: pt.articles,
      relevant: pt.relevant_articles,
      candidates: pt.incident_candidates,
    })),
    recentNews: news.items.map((n) => toSourceItem(n)),
    queue: pending.items.map(toReviewQueueItem),
    sourceHealth: sources.items.map(toSourceSummary),
    lastRuns: activity.recent_runs.map(toIngestionRun),
    mapIncidents: map.incidents.map(mapIncidentToIncident),
  };
}

/* ------------------------------------------------------------------ reviews */

export async function listReviewsLive(q: ReviewQuery): Promise<Paginated<ReviewQueueItem>> {
  const closed = q.state === "approved" || q.state === "rejected";
  const page = closed
    ? await apiRequest<Page<S["IncidentSummary"]>>("GET /api/v1/incidents", {
        query: { ...paging(q), q: q.search, status: q.state, review_priority: q.priority },
      })
    : await apiRequest<Page<S["IncidentSummary"]>>("GET /api/v1/reviews/pending", {
        query: { page: q.page, page_size: q.pageSize, q: q.search, review_priority: q.priority },
      });
  let result = toPaginated(page, toReviewQueueItem);
  if (q.state === "pending" || q.state === "needs_changes") {
    // The queue endpoint lists both; narrow the loaded page to the chosen state.
    result = { ...result, items: result.items.filter((i) => i.state === (q.state as ReviewState)) };
  }
  return result;
}

export async function getReviewCountsLive(): Promise<Record<"pending" | "needs_changes" | "approved" | "rejected", number>> {
  return apiRequest("GET /api/v1/reviews/counts");
}

export async function getPendingReviewCountLive(): Promise<number> {
  const counts = await getReviewCountsLive();
  return counts.pending + counts.needs_changes;
}

export async function getReviewWorkspaceLive(id: string, role: string | null): Promise<ReviewWorkspace> {
  const [{ incident }, bulletins, reviews] = await Promise.all([
    getIncidentLive(id),
    apiRequest<Page<S["BulletinOut"]>>("GET /api/v1/incidents/{id}/bulletins", { params: { id }, query: { page_size: 100 } }),
    apiRequest<Page<S["ReviewOut"]>>("GET /api/v1/incidents/{id}/reviews", { params: { id }, query: { page_size: 100 } }),
  ]);
  // Redacted article text for each piece of evidence (a handful at most).
  const evidenceText = await Promise.all(
    incident.evidence.slice(0, 5).map(async (e) => {
      const item = await apiRequest<S["NewsItemDetail"]>("GET /api/v1/news/{id}", { params: { id: e.sourceItemId } });
      return {
        sourceItemId: e.sourceItemId,
        articleTitle: e.articleTitle,
        publisherName: e.publisherName,
        paragraphs: (item.article_text ?? "").split(/\n+/).map((p) => p.trim()).filter(Boolean),
        run: item.extraction,
      };
    }),
  );
  const primary = incident.evidence.find((e) => e.role === "primary") ?? incident.evidence[0];
  const primaryRun = evidenceText.find((t) => t.sourceItemId === primary?.sourceItemId)?.run ?? null;
  return {
    incident,
    state: incident.reviewState,
    bulletins: bulletins.items.map(toBulletin),
    reviews: reviews.items.map(toReview),
    history: [],
    evidenceText: evidenceText.map((t) => ({
      sourceItemId: t.sourceItemId,
      articleTitle: t.articleTitle,
      publisherName: t.publisherName,
      paragraphs: t.paragraphs,
    })),
    primaryEvent: primaryRun
      ? toExtractedEvent(primaryRun.id, primaryRun.output as Record<string, unknown> | null, primaryRun.extraction_confidence, id)
      : null,
    notes: "",
    canDecide: role === "admin" || role === "editor",
  };
}
