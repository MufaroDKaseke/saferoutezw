/**
 * Maps FastAPI responses (generated types in ../schema.d.ts) onto the view types
 * the screens already use.
 *
 * Rule: a field the backend does not provide becomes null / empty, never an
 * invented value. Anything derived is derived from real fields and says so.
 */
import type {
  ArticleWorkflowState,
  Blackspot,
  BulletinVersion,
  EditorialReview,
  ExtractedEvent,
  ExtractionRun,
  GeoPoint,
  Incident,
  IncidentDetail,
  IncidentEvidence,
  IncidentType,
  IngestionRun,
  KeywordScreeningResult,
  MatchedKeyword,
  NewsClassification,
  PipelineStage,
  ProcessingJob,
  ProcessingStatus,
  ReviewQueueItem,
  ReviewState,
  RiskLevel,
  SourceItem,
  SourceItemDetail,
  SourceSummary,
  VerificationState,
} from "@/types";
import type { ConnectionStatus, RetrievalStatus } from "@/types";
import { INCIDENT_TYPE_LABEL } from "@/lib/formatters/labels";
import type { components } from "../schema";

type S = components["schemas"];

/* ------------------------------------------------------------------ helpers */

export const BLACKSPOT_RADIUS_KM = 0.5;

export function toPaginated<A, B>(
  page: { items: A[]; total: number; page: number; page_size: number },
  map: (item: A) => B,
) {
  return { items: page.items.map(map), total: page.total, page: page.page, pageSize: page.page_size };
}

/** Position accuracy from the provider's stated precision (radius in metres). */
export function accuracyFor(precisionMeters: number | null | undefined): GeoPoint["accuracy"] {
  if (precisionMeters == null) return "approximate";
  if (precisionMeters <= 100) return "exact";
  if (precisionMeters <= 500) return "road_segment";
  if (precisionMeters <= 5000) return "town";
  return "approximate";
}

export function toPoint(
  lat: number,
  lng: number,
  precisionMeters: number | null | undefined,
  confirmed = false,
): GeoPoint {
  // An editor who confirmed a position without stating a precision vouches for it.
  const accuracy = precisionMeters == null && confirmed ? "road_segment" : accuracyFor(precisionMeters);
  return { lat, lng, accuracy, synthetic: false };
}

const titleFor = (type: IncidentType, location: string | null) =>
  location ? `${INCIDENT_TYPE_LABEL[type]} · ${location}` : INCIDENT_TYPE_LABEL[type];

function reviewState(state: S["IncidentSummary"]["review_state"]): ReviewState {
  if (state === "pending_review") return "pending";
  if (state === "archived") return "approved";
  return state;
}

function verification(status: Incident["status"], sourceCount: number): VerificationState {
  if (status === "approved" || status === "published") return "editor_confirmed";
  if (sourceCount >= 2) return "corroborated";
  if (sourceCount === 1) return "single_source";
  return "unverified";
}

/* --------------------------------------------------------------------- news */

const WORKFLOW: Record<ProcessingStatus, ArticleWorkflowState> = {
  pending: "new",
  filtered: "filtered",
  screened: "awaiting_full_text",
  fetch_failed: "failed",
  fetched: "extraction_pending",
  processing: "extraction_pending",
  processed: "processed",
  discarded: "processed",
  failed: "failed",
};

/** The screening reason is stored as "matched: term, term". Groups are not stored, so none is claimed. */
export function toScreening(relevance: S["KeywordRelevance"]): KeywordScreeningResult | null {
  if (relevance.relevant === null) return null;
  const terms = relevance.reason?.startsWith("matched:")
    ? relevance.reason
        .slice("matched:".length)
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean)
    : [];
  const matched: MatchedKeyword[] = terms.map((term) => ({ term, group: "incident", occurrences: 1 }));
  return {
    score: null,
    decision: relevance.relevant ? "relevant" : "not_relevant",
    matchedKeywords: matched,
    rulesetVersion: null,
    screenedAt: null,
  };
}

function retrieval(item: S["NewsItemSummary"]): RetrievalStatus {
  if (item.fetch_status === "ok") return "retrieved";
  if (item.fetch_status === "failed") return "failed";
  return item.processing_status === "filtered" ? "skipped" : "pending";
}

export function toClassification(c: S["NewsClassification"]): NewsClassification {
  return {
    status: c.status as NewsClassification["status"],
    primaryCategory: (c.primary_category ?? null) as NewsClassification["primaryCategory"],
    primarySubtype: c.primary_subtype ?? null,
    candidateCategories: (c.candidate_categories ?? []) as NewsClassification["candidateCategories"],
    recordKind: (c.record_kind ?? null) as NewsClassification["recordKind"],
    geographicScope: (c.geographic_scope ?? null) as NewsClassification["geographicScope"],
    geographicRelevance: c.geographic_relevance ?? null,
    editorialStatus: (c.editorial_status ?? null) as NewsClassification["editorialStatus"],
    intelligenceRecordId: c.intelligence_record_id ?? null,
    linkedIncidentId: c.linked_incident_id ?? null,
  };
}

export function toSourceItem(item: S["NewsItemSummary"], linkedIncidentIds: string[] = []): SourceItem {
  return {
    id: item.id,
    sourceId: item.source_id,
    publisherName: item.publisher,
    sourceKind: item.source_kind,
    ingestionRunId: null,
    externalId: null,
    canonicalUrl: item.source_url,
    titleRedacted: item.headline,
    excerptRedacted: null,
    publishedAt: item.published_at,
    receivedAt: item.ingested_at,
    processingStatus: item.processing_status,
    workflowState: WORKFLOW[item.processing_status],
    screening: toScreening(item.keyword_relevance),
    retrievalStatus: retrieval(item),
    extractionStatus: item.extraction_status ?? "not_started",
    linkedIncidentIds,
    // Older backends do not send the block; leave it out rather than inventing one.
    classification: item.classification ? toClassification(item.classification) : undefined,
    sourcePlatform: item.source_platform,
    synthetic: false,
  };
}

/** Rebuild one ExtractedEvent from the structured model output (a suggestion, not a fact). */
export function toExtractedEvent(
  runId: string,
  output: Record<string, unknown> | null,
  confidence: number | null,
  linkedIncidentId: string | null,
): ExtractedEvent | null {
  if (!output || output.is_road_incident !== true) return null;
  const text = (key: string) => (typeof output[key] === "string" && (output[key] as string).trim() ? (output[key] as string) : null);
  const count = (key: string) => (typeof output[key] === "number" ? String(output[key]) : null);
  const vehicles = typeof output.vehicles_involved === "number" && output.vehicles_involved > 0
    ? [`${output.vehicles_involved} ${output.vehicles_involved === 1 ? "vehicle" : "vehicles"}`]
    : [];
  const on = text("occurred_on");
  const at = text("occurred_time");
  const quotes = Array.isArray(output.evidence_quotes) ? (output.evidence_quotes as unknown[]).filter((q): q is string => typeof q === "string") : [];
  const missing: string[] = [];
  if (!text("location_text")) missing.push("Location");
  if (!on) missing.push("Date of incident");
  if (output.fatalities == null && output.injuries == null) missing.push("Casualty numbers");
  if (!text("cause")) missing.push("Cause");
  return {
    id: runId,
    incidentType: (text("incident_type") ?? "other") as IncidentType,
    locationText: text("location_text"),
    roadName: null,
    kmPeg: null,
    occurredAtText: on ? `${on}${at ? ` ${at}` : ""}` : null,
    occurredAt: on ? `${on}T${at ?? "00:00:00"}` : null,
    vehicles,
    trafficImpact: null,
    injuries: count("injuries"),
    fatalities: count("fatalities"),
    suggestedSeverity: (text("severity") ?? "unknown") as ExtractedEvent["suggestedSeverity"],
    confidence: confidence ?? (typeof output.confidence === "number" ? output.confidence : 0),
    evidenceSnippets: quotes.map((q) => ({ field: "evidence", text: q })),
    missingInformation: missing,
    linkedIncidentId,
  };
}

function toExtractionRun(item: S["NewsItemDetail"], linkedId: string | null): ExtractionRun | null {
  const run = item.extraction;
  if (!run) return null;
  const output = run.output as Record<string, unknown> | null;
  const event = toExtractedEvent(run.id, output, run.extraction_confidence, linkedId);
  const done = run.completed_at ? new Date(run.completed_at).getTime() : null;
  return {
    id: run.id,
    sourceItemId: item.id,
    modelName: run.model_name,
    modelVersion: run.prompt_version,
    status: run.status,
    createdAt: run.created_at,
    durationMs: done ? done - new Date(run.created_at).getTime() : null,
    confidence: run.extraction_confidence,
    classification: output ? (output.is_road_incident ? "road_incident" : "not_road_incident") : null,
    events: event ? [event] : [],
    schemaValidation:
      run.status === "succeeded"
        ? { passed: true, errors: [] }
        : run.status === "failed"
          ? { passed: false, errors: run.error_message ? [run.error_message] : [] }
          : null,
    errorMessage: run.error_message,
  };
}

const REDACTION_MARKS = /\[(NAME|EMAIL|PHONE|ID NUMBER|PLATE)\]/g;

function pipelineFor(item: S["NewsItemDetail"], run: ExtractionRun | null): PipelineStage[] {
  const screened = item.keyword_relevance.relevant;
  const filtered = item.processing_status === "filtered";
  const fetched = item.fetch_status === "ok";
  const failedFetch = item.fetch_status === "failed";
  const stage = (
    id: PipelineStage["id"],
    status: PipelineStage["status"],
    at: string | null = null,
    detail: string | null = null,
  ): PipelineStage => ({ id, status, at, detail });
  const skipped = filtered ? "Filtered out by keyword screening" : null;
  return [
    stage("rss_discovered", "completed", item.ingested_at),
    stage("keyword_screening", screened === null ? "pending" : "completed", null, item.keyword_relevance.reason),
    stage("full_text_retrieval", fetched ? "completed" : failedFetch ? "failed" : filtered ? "skipped" : "pending", item.fetched_at, failedFetch ? item.fetch_error : skipped),
    stage("content_extraction", fetched ? "completed" : failedFetch ? "failed" : filtered ? "skipped" : "pending", item.fetched_at),
    stage("privacy_protection", fetched ? "completed" : filtered ? "skipped" : "pending", item.fetched_at, fetched ? "Personal details masked before storage" : null),
    stage("ai_processing", run ? (run.status === "succeeded" ? "completed" : run.status === "failed" ? "failed" : "pending") : filtered ? "skipped" : "pending", run?.createdAt ?? null, run?.errorMessage ?? null),
    stage("schema_validation", run?.schemaValidation ? (run.schemaValidation.passed ? "completed" : "failed") : filtered ? "skipped" : "pending"),
    stage("incident_candidate", item.incidents.length > 0 ? "completed" : item.processing_status === "processed" || item.processing_status === "discarded" ? "skipped" : "pending", null, item.incidents.length === 0 && item.processing_status === "discarded" ? "Not a road incident" : null),
  ];
}

export function toSourceItemDetail(item: S["NewsItemDetail"]): SourceItemDetail {
  const linkedId = item.incidents[0]?.id ?? null;
  const run = toExtractionRun(item, linkedId);
  const paragraphs = (item.article_text ?? "").split(/\n+/).map((p) => p.trim()).filter(Boolean);
  return {
    ...toSourceItem(item, item.incidents.map((i) => i.id)),
    excerptRedacted: item.excerpt,
    rssTitle: item.headline,
    rssSummary: item.excerpt,
    content: {
      retrievalStatus: retrieval(item),
      retrievedAt: item.fetched_at,
      method: item.fetch_status === "ok" ? "page_fetch" : "none",
      paragraphs,
      wordCount: paragraphs.join(" ").split(/\s+/).filter(Boolean).length,
      redactionCount: (item.article_text ?? "").match(REDACTION_MARKS)?.length ?? 0,
      authors: [],
      imageCount: 0,
      error: item.fetch_error,
    },
    pipeline: pipelineFor(item, run),
    extractionRuns: run ? [run] : [],
    linkedIncidents: item.incidents.map((i) => ({
      id: i.id,
      referenceCode: i.reference_code,
      title: INCIDENT_TYPE_LABEL[i.incident_type],
    })),
  };
}

/* ----------------------------------------------------------------- sources */

export function connectionStatus(source: S["SourceOut"]): ConnectionStatus {
  if (!source.enabled) return "disabled";
  if (!source.last_polled_at) return "untested";
  const successAge = source.last_success_at ? Date.now() - new Date(source.last_success_at).getTime() : Infinity;
  if (source.error_count_7d > 0 && successAge > source.poll_interval_seconds * 2000) return "failing";
  return source.error_count_7d > 0 ? "degraded" : "healthy";
}

export function toSourceSummary(source: S["SourceOut"]): SourceSummary {
  return {
    id: source.id,
    name: source.name,
    kind: source.kind,
    feedUrl: source.feed_url,
    enabled: source.enabled,
    pollIntervalSeconds: source.poll_interval_seconds,
    verificationTier: source.verification_tier,
    rightsNotes: source.rights_notes,
    synthetic: false,
    lastPollAt: source.last_polled_at,
    lastSuccessfulPollAt: source.last_success_at,
    articlesDiscovered: source.article_count,
    errorCount: source.error_count_7d,
    connectionStatus: connectionStatus(source),
    lastError: source.last_error,
  };
}

export function toIngestionRun(run: S["IngestionRunOut"]): IngestionRun {
  return {
    id: run.id,
    sourceId: run.source_id,
    sourceName: run.source_name,
    startedAt: run.started_at,
    completedAt: run.completed_at,
    status: run.status,
    fetchedCount: run.fetched_count,
    insertedCount: run.inserted_count,
    duplicateCount: run.duplicate_count,
    errorCount: run.error_count,
    errorMessage: run.error_message,
    trigger: "scheduled",
  };
}

/* -------------------------------------------------------------- processing */

export function toProcessingJob(run: S["ProcessingRun"]): ProcessingJob {
  const ingestion = run.kind === "ingestion";
  const started = new Date(run.started_at).getTime();
  const ended = run.completed_at ? new Date(run.completed_at).getTime() : null;
  return {
    id: run.id,
    kind: ingestion ? "rss_poll" : "ai_extraction",
    status: run.status as ProcessingJob["status"],
    sourceId: run.source_id ?? "",
    sourceName: run.source_name ?? "",
    sourceItemId: run.source_item_id,
    subject: ingestion ? (run.source_name ?? "Source") : (run.headline ?? "Article"),
    startedAt: run.started_at,
    durationMs: ended ? ended - started : null,
    summary: ingestion
      ? `${run.fetched_count ?? 0} fetched, ${run.inserted_count ?? 0} new, ${run.duplicate_count ?? 0} duplicates`
      : `${run.model_name ?? "model"}${run.extraction_confidence != null ? ` · confidence ${run.extraction_confidence.toFixed(2)}` : ""}`,
    errorMessage: run.error_message,
    retryCount: 0,
    retryable: false,
    ingestionRunId: ingestion ? run.id : null,
  };
}

/* --------------------------------------------------------------- incidents */

export function toIncident(i: S["IncidentSummary"], point: GeoPoint | null = null): Incident {
  return {
    id: i.id,
    referenceCode: i.reference_code,
    title: titleFor(i.incident_type, i.location_text),
    incidentType: i.incident_type,
    severity: i.severity,
    locationText: i.location_text,
    roadName: null,
    province: null,
    point,
    occurredAt: i.occurred_at,
    occurredAtNote: null,
    credibilityScore: i.credibility_score,
    credibilityRationale: null,
    geographicRiskScore: i.geographic_risk_score,
    riskLevel: null,
    reviewPriority: i.review_priority,
    status: i.status,
    reviewState: reviewState(i.review_state),
    verification: verification(i.status, i.source_count),
    summary: i.summary ?? "",
    vehicles: [],
    trafficImpact: null,
    missingInformation: [],
    sourceCount: i.source_count,
    createdAt: i.created_at,
    updatedAt: i.updated_at,
    synthetic: false,
  };
}

export function toReviewQueueItem(i: S["IncidentSummary"]): ReviewQueueItem {
  return {
    incidentId: i.id,
    referenceCode: i.reference_code,
    title: titleFor(i.incident_type, i.location_text),
    incidentType: i.incident_type,
    locationText: i.location_text,
    priority: i.review_priority,
    state: reviewState(i.review_state),
    sourceCount: i.source_count,
    missingInformationCount: i.missing_information_count,
    riskLevel: null,
    extractionConfidence: i.extraction_confidence,
    receivedAt: i.created_at,
    assignedTo: null,
    latestBulletinVersion: i.latest_bulletin_version,
  };
}

const RISK_ORDER: RiskLevel[] = ["low", "medium", "high", "critical"];

export function toEvidence(incidentId: string, e: S["EvidenceOut"]): IncidentEvidence {
  const quotes = (e.extraction_output as { evidence_quotes?: unknown } | null)?.evidence_quotes;
  return {
    id: e.id,
    incidentId,
    sourceItemId: e.source_item.id,
    role: e.role,
    articleTitle: e.source_item.headline,
    publisherName: e.source_item.publisher,
    publishedAt: e.source_item.published_at,
    canonicalUrl: e.source_item.source_url,
    snippet: Array.isArray(quotes) && typeof quotes[0] === "string" ? quotes[0] : null,
    extractionRunId: null,
    extractedEventId: null,
  };
}

export function toIncidentDetail(
  detail: S["IncidentDetail"],
  evidence: S["EvidenceOut"][],
  matches: S["BlackspotMatchesOut"],
): IncidentDetail {
  const loc = detail.location;
  const point = loc.coordinates
    ? toPoint(loc.coordinates.latitude, loc.coordinates.longitude, loc.precision_meters, loc.confirmed_by_editor)
    : null;
  const strongest = matches.matches
    .map((m) => m.blackspot.risk_level)
    .sort((a, b) => RISK_ORDER.indexOf(b) - RISK_ORDER.indexOf(a))[0];
  return {
    ...toIncident(detail, point),
    missingInformation: detail.missing_information,
    vehicles:
      detail.extracted_facts?.vehicles_involved && detail.extracted_facts.vehicles_involved > 0
        ? [`${detail.extracted_facts.vehicles_involved} ${detail.extracted_facts.vehicles_involved === 1 ? "vehicle" : "vehicles"}`]
        : [],
    riskLevel: strongest ?? null,
    evidence: evidence.map((e) => toEvidence(detail.id, e)),
    blackspotMatches: matches.matches.map((m) => ({
      blackspotId: m.blackspot.id,
      code: m.blackspot.id.slice(0, 8).toUpperCase(),
      name: m.blackspot.name,
      distanceKm: m.distance_meters / 1000,
    })),
    locationInfo: {
      status: loc.status,
      source: loc.source,
      method: loc.resolution_method,
      precisionMeters: loc.precision_meters,
      note: loc.note,
      confirmedByEditor: loc.confirmed_by_editor,
      candidates: loc.candidates.map((c) => ({
        label: c.label,
        latitude: c.latitude,
        longitude: c.longitude,
        precisionMeters: c.precision_meters ?? null,
        source: c.source,
      })),
    },
    extractionConfidence: detail.assessments.extraction_confidence,
    extractionModel: detail.extracted_facts?.model_name ?? null,
  };
}

/** A map marker as a thin Incident: only what the map and its side panel need. */
export function mapIncidentToIncident(m: S["MapIncident"]): Incident {
  const base = toIncident(
    {
      id: m.id,
      reference_code: m.reference_code,
      incident_type: m.incident_type,
      severity: m.severity,
      status: m.status,
      review_state: m.status === "approved" || m.status === "published" ? "approved" : "pending_review",
      review_priority: "normal",
      summary: null,
      location_text: m.label,
      location_status: m.location_status,
      has_coordinates: true,
      occurred_at: m.occurred_at,
      created_at: m.occurred_at ?? new Date(0).toISOString(),
      updated_at: m.occurred_at ?? new Date(0).toISOString(),
      source_count: 0,
      credibility_score: null,
      geographic_risk_score: null,
      latest_bulletin_version: null,
      extraction_confidence: null,
      missing_information_count: 0,
    },
    toPoint(m.latitude, m.longitude, m.precision_meters, m.marker_kind !== "candidate"),
  );
  return { ...base, verification: m.marker_kind === "candidate" ? "unverified" : "editor_confirmed" };
}

export function toBlackspot(b: S["BlackspotOut"]): Blackspot {
  return {
    id: b.id,
    code: b.id.slice(0, 8).toUpperCase(),
    name: b.name,
    roadName: null,
    province: null,
    riskLevel: b.risk_level,
    point: { lat: b.latitude, lng: b.longitude, accuracy: "exact", synthetic: false },
    radiusKm: BLACKSPOT_RADIUS_KM,
    observationPeriod: { from: b.observation_period_start, to: b.observation_period_end },
    dataSourceName: b.source_name,
    sourceReference: b.source_reference ?? "",
    synthetic: false,
    nearbyIncidentCount: b.nearby_incident_count,
    notes: b.description,
  };
}

/* --------------------------------------------------------------- editorial */

export function toBulletin(b: S["BulletinOut"]): BulletinVersion {
  return {
    id: b.id,
    incidentId: b.incident_id,
    versionNumber: b.version_number,
    headline: b.headline,
    body: b.body,
    createdBy: b.created_by,
    createdByName: b.created_by_name ?? "Unknown",
    createdAt: b.created_at,
  };
}

export function toReview(r: S["ReviewOut"]): EditorialReview {
  return {
    id: r.id,
    incidentId: r.incident_id,
    bulletinVersionId: r.bulletin_version_id,
    reviewerId: r.reviewer_id,
    reviewerName: r.reviewer_name ?? "Unknown",
    decision: r.decision,
    notes: r.notes,
    reviewedAt: r.reviewed_at,
  };
}
