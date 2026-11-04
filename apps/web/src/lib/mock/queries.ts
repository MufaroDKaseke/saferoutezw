import { NotFoundError } from "@/lib/api/errors";
import type {
  AlertQuery,
  BlackspotQuery,
  IncidentQuery,
  MapQuery,
  NewsQuery,
  ProcessingQuery,
  ReviewQuery,
  DateRangeKey,
} from "@/lib/api/types";
import { REVIEWER_ROLES } from "@/types";
import type {
  ActivityPoint,
  AuditEvent,
  Blackspot,
  DashboardRange,
  DashboardSummary,
  Incident,
  IncidentDetail,
  Paginated,
  ProcessingBacklog,
  ProcessingJob,
  PublicAlert,
  ReviewQueueItem,
  ReviewWorkspace,
  SourceItem,
  SourceItemDetail,
  SourceSummary,
  IngestionRun,
} from "@/types";
import { DEMO_NOW } from "./clock";
import { DEMO_USER } from "./data/people-sources";
import { getDb, getNotes } from "./store";
import { inRange, matchesSearch, paginate, rangeStart, sortItems } from "./query-utils";

/* ---------------------------------------------------------------- news */

function toListItem(a: SourceItemDetail): SourceItem {
  // Lists never carry article bodies or extraction output.
  return {
    id: a.id,
    sourceId: a.sourceId,
    publisherName: a.publisherName,
    sourceKind: a.sourceKind,
    ingestionRunId: a.ingestionRunId,
    externalId: a.externalId,
    canonicalUrl: a.canonicalUrl,
    titleRedacted: a.titleRedacted,
    excerptRedacted: a.excerptRedacted,
    publishedAt: a.publishedAt,
    receivedAt: a.receivedAt,
    processingStatus: a.processingStatus,
    workflowState: a.workflowState,
    screening: a.screening,
    retrievalStatus: a.retrievalStatus,
    extractionStatus: a.extractionStatus,
    linkedIncidentIds: a.linkedIncidentIds,
    synthetic: a.synthetic,
  };
}

export function listNews(q: NewsQuery): Paginated<SourceItem> {
  const kw = q.keyword?.trim().toLowerCase();
  const filtered = getDb().articles.filter(
    (a) =>
      matchesSearch(q.search, a.titleRedacted, a.publisherName, a.excerptRedacted) &&
      (!q.publisherId || a.sourceId === q.publisherId) &&
      (!q.relevance || a.screening?.decision === q.relevance) &&
      (!q.status || a.workflowState === q.status) &&
      inRange(a.receivedAt, q.range) &&
      (!kw || !!a.screening?.matchedKeywords.some((m) => m.term.toLowerCase().includes(kw))),
  );
  const sorted = sortItems(
    filtered,
    {
      receivedAt: (a) => a.receivedAt,
      publishedAt: (a) => a.publishedAt,
      title: (a) => a.titleRedacted,
      publisher: (a) => a.publisherName,
      score: (a) => a.screening?.score ?? null,
    },
    q.sort,
    q.dir,
    { sort: "receivedAt", dir: "desc" },
  );
  const page = paginate(sorted, q);
  return { ...page, items: page.items.map(toListItem) };
}

export function getNews(id: string): SourceItemDetail {
  const item = getDb().articles.find((a) => a.id === id);
  if (!item) throw new NotFoundError("Article");
  return item;
}

/* ----------------------------------------------------------- incidents */

export function listIncidents(q: IncidentQuery): Paginated<Incident> {
  const filtered = getDb().incidents.filter(
    (i) =>
      matchesSearch(q.search, i.referenceCode, i.title, i.locationText, i.roadName) &&
      (!q.reviewState || i.reviewState === q.reviewState) &&
      (!q.type || i.incidentType === q.type) &&
      (!q.province || i.province === q.province) &&
      (!q.severity || i.severity === q.severity) &&
      (!q.verification || i.verification === q.verification) &&
      inRange(i.occurredAt ?? i.createdAt, q.range),
  );
  const severityRank = { unknown: 0, minor: 1, serious: 2, fatal: 3 } as const;
  const sorted = sortItems(
    filtered,
    {
      reference: (i) => i.referenceCode,
      createdAt: (i) => i.createdAt,
      occurredAt: (i) => i.occurredAt ?? i.createdAt,
      severity: (i) => severityRank[i.severity],
      sources: (i) => i.sourceCount,
      risk: (i) => i.geographicRiskScore,
    },
    q.sort,
    q.dir,
    { sort: "createdAt", dir: "desc" },
  );
  return paginate(sorted, q);
}

function detailOf(incident: Incident): IncidentDetail {
  const db = getDb();
  const evidence = db.evidence.filter((e) => e.incidentId === incident.id);
  const primary = evidence.find((e) => e.role === "primary") ?? evidence[0];
  const article = primary ? db.articles.find((a) => a.id === primary.sourceItemId) : undefined;
  const run = article?.extractionRuns.find((r) => r.status === "succeeded");
  return {
    ...incident,
    evidence,
    blackspotMatches: db.blackspotMatches[incident.id] ?? [],
    extractionConfidence: run?.confidence ?? null,
    extractionModel: run?.modelName ?? null,
  };
}

export function getIncident(id: string): IncidentDetail {
  const incident = getDb().incidents.find((i) => i.id === id);
  if (!incident) throw new NotFoundError("Incident");
  return detailOf(incident);
}

export function getIncidentAudit(incidentId: string): AuditEvent[] {
  return getDb().audit.filter((a) => a.entityId === incidentId);
}

/* ----------------------------------------------------------------- map */

export interface MapData {
  incidents: Incident[];
  alertIncidentIds: string[];
  blackspots: Blackspot[];
}

/**
 * Layers are kept distinct: unverified candidates, reviewed incidents and
 * approved public alerts. Rejected incidents are never returned.
 */
export function listMapData(q: MapQuery): MapData {
  const db = getDb();
  const incidents = db.incidents.filter(
    (i) =>
      !!i.point &&
      i.status !== "rejected" &&
      i.status !== "archived" &&
      (!q.severity || i.severity === q.severity) &&
      matchesSearch(q.search, i.referenceCode, i.title, i.locationText, i.roadName) &&
      inRange(i.occurredAt ?? i.createdAt, q.range),
  );
  return {
    incidents,
    alertIncidentIds: db.alerts.map((a) => a.incidentId),
    blackspots: db.blackspots,
  };
}

/* ------------------------------------------------------------- reviews */

const PRIORITY_RANK = { urgent: 3, high: 2, normal: 1, low: 0 } as const;

function toQueueItem(incident: Incident): ReviewQueueItem {
  const db = getDb();
  const detail = detailOf(incident);
  const primary = detail.evidence.find((e) => e.role === "primary") ?? detail.evidence[0];
  const article = db.articles.find((a) => a.id === primary?.sourceItemId);
  const bulletins = db.bulletins.filter((b) => b.incidentId === incident.id);
  const opener = [...db.audit]
    .reverse()
    .find((a) => a.entityId === incident.id && a.action === "opened_for_review");
  return {
    incidentId: incident.id,
    referenceCode: incident.referenceCode,
    title: incident.title,
    incidentType: incident.incidentType,
    locationText: incident.locationText,
    priority: incident.reviewPriority,
    state: incident.reviewState,
    sourceCount: incident.sourceCount,
    missingInformationCount: incident.missingInformation.length,
    riskLevel: incident.riskLevel,
    extractionConfidence: detail.extractionConfidence,
    receivedAt: article?.receivedAt ?? incident.createdAt,
    assignedTo: incident.reviewState === "approved" || incident.reviewState === "rejected" ? null : (opener?.actorName ?? null),
    latestBulletinVersion: bulletins.length ? Math.max(...bulletins.map((b) => b.versionNumber)) : null,
  };
}

export function listReviews(q: ReviewQuery): Paginated<ReviewQueueItem> {
  const items = getDb()
    .incidents.map(toQueueItem)
    .filter(
      (r) =>
        matchesSearch(q.search, r.referenceCode, r.title, r.locationText) &&
        (!q.priority || r.priority === q.priority) &&
        (!q.state ||
          (q.state === "open" ? r.state === "pending" || r.state === "needs_changes" : r.state === q.state)),
    );
  const sorted = sortItems(
    items,
    {
      priority: (r) => PRIORITY_RANK[r.priority],
      received: (r) => r.receivedAt,
      reference: (r) => r.referenceCode,
      sources: (r) => r.sourceCount,
      missing: (r) => r.missingInformationCount,
    },
    q.sort,
    q.dir,
    { sort: "priority", dir: "desc" },
  );
  return paginate(sorted, q);
}

export function getReviewCounts(): Record<"pending" | "needs_changes" | "approved" | "rejected", number> {
  const counts = { pending: 0, needs_changes: 0, approved: 0, rejected: 0 };
  for (const i of getDb().incidents) counts[i.reviewState] += 1;
  return counts;
}

export function getReviewWorkspace(incidentId: string): ReviewWorkspace {
  const db = getDb();
  const incident = getIncident(incidentId);
  const bulletins = db.bulletins
    .filter((b) => b.incidentId === incidentId)
    .sort((a, b) => b.versionNumber - a.versionNumber);
  const reviews = db.reviews
    .filter((r) => r.incidentId === incidentId)
    .sort((a, b) => b.reviewedAt.localeCompare(a.reviewedAt));
  const evidenceText = incident.evidence.map((e) => {
    const article = db.articles.find((a) => a.id === e.sourceItemId);
    return {
      sourceItemId: e.sourceItemId,
      articleTitle: e.articleTitle,
      publisherName: e.publisherName,
      paragraphs: article?.content.paragraphs ?? [],
    };
  });
  const primary = incident.evidence.find((e) => e.role === "primary") ?? incident.evidence[0];
  const primaryEvent =
    db.articles
      .find((a) => a.id === primary?.sourceItemId)
      ?.extractionRuns.flatMap((r) => r.events)
      .find((ev) => ev.id === primary?.extractedEventId) ?? null;
  return {
    incident,
    state: incident.reviewState,
    primaryEvent,
    bulletins,
    reviews,
    history: getIncidentAudit(incidentId),
    evidenceText,
    notes: getNotes(incidentId),
    canDecide: REVIEWER_ROLES.includes(DEMO_USER.role),
  };
}

export function getPendingReviewCount(): number {
  return getDb().incidents.filter((i) => i.reviewState === "pending").length;
}

/* ----------------------------------------------------------- blackspots */

export function listBlackspots(q: BlackspotQuery): Paginated<Blackspot> {
  const filtered = getDb().blackspots.filter(
    (b) =>
      matchesSearch(q.search, b.code, b.name, b.roadName, b.province) &&
      (!q.risk || b.riskLevel === q.risk) &&
      (!q.province || b.province === q.province),
  );
  const riskRank = { low: 0, medium: 1, high: 2, critical: 3 } as const;
  const sorted = sortItems(
    filtered,
    {
      code: (b) => b.code,
      risk: (b) => riskRank[b.riskLevel],
      road: (b) => b.roadName,
      nearby: (b) => b.nearbyIncidentCount,
    },
    q.sort,
    q.dir,
    { sort: "code", dir: "asc" },
  );
  return paginate(sorted, { pageSize: 50, ...q });
}

/* -------------------------------------------------------------- alerts */

export function listAlerts(q: AlertQuery): Paginated<PublicAlert> {
  const filtered = getDb().alerts.filter(
    (a) =>
      matchesSearch(q.search, a.reference, a.headline, a.locationText, a.incidentReference) &&
      (!q.state || a.publicationState === q.state) &&
      (!q.channel || a.channels.some((c) => c.channel === q.channel)),
  );
  const sorted = sortItems(
    filtered,
    {
      approvedAt: (a) => a.approvedAt,
      reference: (a) => a.reference,
      headline: (a) => a.headline,
    },
    q.sort,
    q.dir,
    { sort: "approvedAt", dir: "desc" },
  );
  return paginate(sorted, q);
}

export function getAlert(id: string): PublicAlert {
  const alert = getDb().alerts.find((a) => a.id === id);
  if (!alert) throw new NotFoundError("Alert");
  return alert;
}

/** Incidents approved by an editor that have no alert record yet are impossible; kept for the KPI. */
export function countAwaitingApproval(): number {
  return getDb().incidents.filter((i) => i.reviewState === "pending" || i.reviewState === "needs_changes").length;
}

/* ------------------------------------------------------------- sources */

export function listSources(): SourceSummary[] {
  return getDb().sources;
}

export function listIngestionHistory(sourceId: string, limit = 30): IngestionRun[] {
  return getDb()
    .ingestionRuns.filter((r) => r.sourceId === sourceId)
    .slice(0, limit);
}

/* ---------------------------------------------------------- processing */

export function listProcessing(q: ProcessingQuery): Paginated<ProcessingJob> {
  const filtered = getDb().jobs.filter(
    (j) =>
      matchesSearch(q.search, j.subject, j.sourceName, j.summary, j.errorMessage) &&
      (!q.kind || j.kind === q.kind) &&
      (!q.status || j.status === q.status) &&
      (!q.sourceId || j.sourceId === q.sourceId) &&
      inRange(j.startedAt, q.range),
  );
  const sorted = sortItems(
    filtered,
    {
      startedAt: (j) => j.startedAt,
      duration: (j) => j.durationMs,
      source: (j) => j.sourceName,
      status: (j) => j.status,
    },
    q.sort,
    q.dir,
    { sort: "startedAt", dir: "desc" },
  );
  return paginate(sorted, { pageSize: 12, ...q });
}

export function getBacklog(): ProcessingBacklog {
  const articles = getDb().articles;
  return {
    awaitingScreening: articles.filter((a) => a.workflowState === "new").length,
    awaitingFullText: articles.filter((a) => a.workflowState === "awaiting_full_text").length,
    awaitingExtraction: articles.filter(
      (a) => a.workflowState === "extraction_pending" || a.workflowState === "full_text_retrieved",
    ).length,
    failedNeedingAttention: articles.filter((a) => a.workflowState === "failed").length,
  };
}

/* ----------------------------------------------------------- dashboard */

function buckets(range: DashboardRange): { start: number; end: number }[] {
  const end = DEMO_NOW.getTime();
  if (range === "24h") {
    const step = 3 * 3_600_000;
    return Array.from({ length: 8 }, (_, i) => ({ start: end - (8 - i) * step, end: end - (7 - i) * step }));
  }
  const days = range === "7d" ? 7 : 30;
  // Day buckets aligned to Harare midnight (UTC+2).
  const offset = 2 * 3_600_000;
  const todayStart = Math.floor((end + offset) / 86_400_000) * 86_400_000 - offset;
  return Array.from({ length: days }, (_, i) => {
    const start = todayStart - (days - 1 - i) * 86_400_000;
    return { start, end: start + 86_400_000 };
  });
}

export function getDashboard(range: DashboardRange): DashboardSummary {
  const db = getDb();
  const start = rangeStart(range as DateRangeKey) ?? 0;
  const articles = db.articles.filter((a) => new Date(a.receivedAt).getTime() >= start);
  const pending = db.incidents.filter((i) => i.reviewState === "pending");
  const queue = db.incidents
    .filter((i) => i.reviewState === "pending")
    .map(toQueueItem)
    .sort(
      (a, b) =>
        PRIORITY_RANK[b.priority] - PRIORITY_RANK[a.priority] || b.receivedAt.localeCompare(a.receivedAt),
    );

  const oldest = pending.length
    ? Math.max(...pending.map((i) => (DEMO_NOW.getTime() - new Date(i.createdAt).getTime()) / 86_400_000))
    : null;

  const activity: ActivityPoint[] = buckets(range).map(({ start: s, end: e }) => {
    const inBucket = db.articles.filter((a) => {
      const t = new Date(a.receivedAt).getTime();
      return t > s && t <= e;
    });
    const cands = db.incidents.filter((i) => {
      const t = new Date(i.createdAt).getTime();
      return t > s && t <= e;
    });
    return {
      // Day buckets are labelled by their start; 3-hour buckets by their end.
      date: new Date(range === "24h" ? e : s).toISOString(),
      articles: inBucket.length,
      relevant: inBucket.filter((a) => a.screening?.decision === "relevant").length,
      candidates: cands.length,
    };
  });

  return {
    range,
    asOf: DEMO_NOW.toISOString(),
    kpis: {
      articlesIngested: articles.length,
      roadRelevantArticles: articles.filter((a) => a.screening?.decision === "relevant").length,
      incidentCandidates: db.incidents.filter((i) => new Date(i.createdAt).getTime() >= start).length,
      pendingReviews: pending.length,
      highPriorityPending: pending.filter((i) => i.reviewPriority === "high" || i.reviewPriority === "urgent").length,
      oldestPendingDays: oldest === null ? null : Math.round(oldest),
      approvedAlerts: db.alerts.length,
      failedJobs: db.articles.filter((a) => a.workflowState === "failed").length,
    },
    pipeline: {
      ingested: articles.length,
      aiExtracted: articles.filter((a) => a.extractionStatus === "succeeded").length,
      awaitingDecision: pending.length,
      approvedByEditor: db.incidents.filter((i) => i.reviewState === "approved").length,
      fullyShared: db.alerts.filter((a) => a.publicationState === "published").length,
    },
    activity,
    recentNews: [...db.articles]
      .sort((a, b) => b.receivedAt.localeCompare(a.receivedAt))
      .slice(0, 6)
      .map(toListItem),
    queue: queue.slice(0, 4),
    sourceHealth: db.sources,
    lastRuns: db.ingestionRuns.slice(0, 5),
    mapIncidents: db.incidents.filter((i) => !!i.point && i.status !== "rejected" && i.status !== "archived"),
  };
}

