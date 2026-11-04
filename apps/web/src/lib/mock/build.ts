import {
  deriveAlertState,
  deriveReviewState,
  deriveVerification,
  deriveWorkflowState,
  RELEVANCE_THRESHOLD,
  riskLevelFromScore,
} from "@/lib/domain/derive";
import type {
  AuditEvent,
  Blackspot,
  BulletinVersion,
  ChannelDelivery,
  ConnectionStatus,
  EditorialReview,
  ExtractionRun,
  Incident,
  IncidentEvidence,
  IngestionRun,
  PipelineStage,
  ProcessingJob,
  ProcessingStatus,
  PublicAlert,
  SourceItemDetail,
  SourceSummary,
} from "@/types";
import { cat, DEMO_NOW, haversineKm, seeded } from "./clock";
import { ARTICLES, type ArticleSeed } from "./data/articles";
import { BLACKSPOT_DATA_SOURCE, BLACKSPOT_SEEDS } from "./data/blackspots";
import { ALERTS, BULLETINS, INCIDENTS, REVIEWS } from "./data/incidents";
import { AI_ACTOR, DEMO_USER, OTHER_REVIEWERS, SOURCES, SYSTEM_ACTOR } from "./data/people-sources";

export const DEMO_MODEL_NAME = "demo-extraction-model";
export const DEMO_MODEL_VERSION = "fixture-1.0";
/** Distance within which a blackspot counts as context for an incident. */
export const BLACKSPOT_MATCH_KM = 10;

export interface MockDb {
  sources: SourceSummary[];
  ingestionRuns: IngestionRun[];
  articles: SourceItemDetail[];
  incidents: Incident[];
  evidence: IncidentEvidence[];
  bulletins: BulletinVersion[];
  reviews: EditorialReview[];
  alerts: PublicAlert[];
  blackspots: Blackspot[];
  audit: AuditEvent[];
  jobs: ProcessingJob[];
  /** Blackspot context per incident, computed once. */
  blackspotMatches: Record<string, { blackspotId: string; code: string; name: string; distanceKm: number }[]>;
}

const addMinutes = (iso: string, minutes: number) =>
  new Date(new Date(iso).getTime() + minutes * 60_000).toISOString();

const wordCount = (paragraphs: string[]) =>
  paragraphs.join(" ").split(/\s+/).filter(Boolean).length;

const userName = (key: "ai" | "tendai" | "rudo") =>
  key === "ai" ? AI_ACTOR.name : key === "tendai" ? DEMO_USER.name : OTHER_REVIEWERS[0].name;
const userId = (key: "ai" | "tendai" | "rudo") =>
  key === "ai" ? AI_ACTOR.id : key === "tendai" ? DEMO_USER.id : OTHER_REVIEWERS[0].id;

function entryRef(seed: string): string {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0).toString(16).padStart(8, "0").slice(0, 4);
}

/* ------------------------------------------------------------------ articles */

function buildPipeline(seed: ArticleSeed, received: string): PipelineStage[] {
  const sourceName = SOURCES.find((s) => s.id === seed.sourceId)?.name ?? "source";
  const screen = seed.screen;
  const relevant = !!screen && screen.score >= RELEVANCE_THRESHOLD;
  const stage = (
    id: PipelineStage["id"],
    status: PipelineStage["status"],
    offsetMin: number | null,
    detail: string | null,
  ): PipelineStage => ({
    id,
    status,
    at: status === "completed" || status === "failed" ? addMinutes(received, offsetMin ?? 0) : null,
    detail,
  });

  const stages: PipelineStage[] = [
    stage("rss_discovered", "completed", 0, `Found in a scheduled poll of ${sourceName}.`),
  ];

  if (!screen) {
    stages.push(stage("keyword_screening", "pending", null, "Waiting for the next screening pass."));
    for (const id of [
      "full_text_retrieval",
      "content_extraction",
      "privacy_protection",
      "ai_processing",
      "schema_validation",
      "incident_candidate",
    ] as const) {
      stages.push(stage(id, "pending", null, null));
    }
    return stages;
  }

  stages.push(
    stage(
      "keyword_screening",
      "completed",
      0.5,
      relevant
        ? `Score ${screen.score.toFixed(2)}, relevant. ${screen.keywords.length} keyword${screen.keywords.length === 1 ? "" : "s"} matched.`
        : `Score ${screen.score.toFixed(2)}, below the ${RELEVANCE_THRESHOLD.toFixed(2)} threshold. Not read further.`,
    ),
  );

  if (!relevant) {
    for (const id of [
      "full_text_retrieval",
      "content_extraction",
      "privacy_protection",
      "ai_processing",
      "schema_validation",
      "incident_candidate",
    ] as const) {
      stages.push(stage(id, "skipped", null, "Skipped because the article was filtered out."));
    }
    return stages;
  }

  if (seed.retrieval === "failed") {
    stages.push(stage("full_text_retrieval", "failed", 1, seed.retrievalError ?? "Retrieval failed."));
    for (const id of [
      "content_extraction",
      "privacy_protection",
      "ai_processing",
      "schema_validation",
      "incident_candidate",
    ] as const) {
      stages.push(stage(id, "skipped", null, "Not reached: the full article could not be retrieved."));
    }
    return stages;
  }

  const words = wordCount(seed.paragraphs);
  stages.push(
    stage("full_text_retrieval", "completed", 1.5, `Fetched from the publisher (${seed.retrievalMethod ?? "page_fetch"}).`),
    stage("content_extraction", "completed", 1.7, `Readable text extracted, ${words} words.`),
    stage(
      "privacy_protection",
      "completed",
      1.8,
      seed.redactions
        ? `${seed.redactions} personal detail${seed.redactions === 1 ? "" : "s"} masked before AI processing.`
        : "No personal details found.",
    ),
  );

  if (seed.extraction === "pending" || seed.extraction === "none") {
    stages.push(
      stage("ai_processing", "pending", null, "Queued for AI extraction."),
      stage("schema_validation", "pending", null, null),
      stage("incident_candidate", "pending", null, null),
    );
    return stages;
  }
  if (seed.extraction === "failed") {
    stages.push(
      stage("ai_processing", "completed", 5, "Model responded."),
      stage("schema_validation", "failed", 5.1, seed.extractionError ?? "Validation failed."),
      stage("incident_candidate", "skipped", null, "Not created: the output failed validation."),
    );
    return stages;
  }

  const created = (seed.events ?? []).filter((e) => e.linkedIncidentId).length;
  stages.push(
    stage("ai_processing", "completed", 5, `Extraction completed at ${Math.round((seed.confidence ?? 0) * 100)}% model confidence.`),
    stage("schema_validation", "completed", 5.1, "Output matched the expected schema."),
    created > 0
      ? stage("incident_candidate", "completed", 5.5, `${created} incident candidate${created === 1 ? "" : "s"} created for review.`)
      : stage(
          "incident_candidate",
          "skipped",
          null,
          seed.classification === "not_road_incident"
            ? "No incident: the model classed this as not describing a road incident."
            : "No incident candidate: confidence was below the candidate threshold.",
        ),
  );
  return stages;
}

function buildArticle(seed: ArticleSeed, rand: () => number): SourceItemDetail {
  const source = SOURCES.find((s) => s.id === seed.sourceId)!;
  const received = cat(seed.receivedCat);
  const screening = seed.screen
    ? {
        score: seed.screen.score,
        decision: (seed.screen.score >= RELEVANCE_THRESHOLD ? "relevant" : "not_relevant") as "relevant" | "not_relevant",
        matchedKeywords: seed.screen.keywords.map(([term, group, occurrences]) => ({ term, group, occurrences })),
        rulesetVersion: "zw-road-keywords-demo-3",
        screenedAt: addMinutes(received, 0.5),
      }
    : null;

  const extractionStatus = seed.extraction === "none" ? "not_started" : seed.extraction;

  const runs: ExtractionRun[] = [];
  if (seed.extraction === "succeeded") {
    runs.push({
      id: `run-${seed.id}-1`,
      sourceItemId: seed.id,
      modelName: DEMO_MODEL_NAME,
      modelVersion: DEMO_MODEL_VERSION,
      status: "succeeded",
      createdAt: addMinutes(received, 5),
      durationMs: Math.round(3000 + rand() * 6000),
      confidence: seed.confidence ?? null,
      classification: seed.classification ?? "road_incident",
      events: (seed.events ?? []).map((e) => ({
        ...e,
        occurredAt: e.occurredAtCat ? cat(e.occurredAtCat) : null,
      })),
      schemaValidation: { passed: true, errors: [] },
      errorMessage: null,
    });
  } else if (seed.extraction === "failed") {
    for (const attempt of [1, 2]) {
      runs.push({
        id: `run-${seed.id}-${attempt}`,
        sourceItemId: seed.id,
        modelName: DEMO_MODEL_NAME,
        modelVersion: DEMO_MODEL_VERSION,
        status: "failed",
        createdAt: addMinutes(received, attempt === 1 ? 5 : 12),
        durationMs: Math.round(2500 + rand() * 3000),
        confidence: null,
        classification: null,
        events: [],
        schemaValidation: { passed: false, errors: seed.schemaErrors ?? [] },
        errorMessage: seed.extractionError ?? "Extraction failed.",
      });
    }
  } else if (seed.extraction === "pending") {
    runs.push({
      id: `run-${seed.id}-1`,
      sourceItemId: seed.id,
      modelName: DEMO_MODEL_NAME,
      modelVersion: DEMO_MODEL_VERSION,
      status: "pending",
      createdAt: addMinutes(received, 5),
      durationMs: null,
      confidence: null,
      classification: null,
      events: [],
      schemaValidation: null,
      errorMessage: null,
    });
  }

  const workflowState = deriveWorkflowState({
    screening,
    retrieval: seed.retrieval,
    extraction: extractionStatus,
  });
  const processingStatus: ProcessingStatus =
    workflowState === "filtered"
      ? "discarded"
      : workflowState === "failed"
        ? "failed"
        : workflowState === "processed"
          ? "processed"
          : workflowState === "extraction_pending"
            ? "processing"
            : "pending";

  const linkedIncidentIds = Array.from(
    new Set(INCIDENTS.filter((i) => i.evidence.some((e) => e.articleId === seed.id)).map((i) => i.id)),
  );

  const paragraphs = seed.paragraphs;
  return {
    id: seed.id,
    sourceId: seed.sourceId,
    publisherName: source.name,
    sourceKind: source.kind,
    ingestionRunId: null,
    externalId: `${seed.sourceId}:${seed.id}`,
    canonicalUrl: `${new URL(source.feedUrl ?? "https://demo.example").origin}/news/${seed.id}`,
    titleRedacted: seed.title,
    excerptRedacted: seed.excerpt,
    publishedAt: cat(seed.publishedCat),
    receivedAt: received,
    processingStatus,
    workflowState,
    screening,
    retrievalStatus: seed.retrieval,
    extractionStatus,
    linkedIncidentIds,
    synthetic: true,
    rssTitle: seed.title,
    rssSummary: seed.excerpt,
    content: {
      retrievalStatus: seed.retrieval,
      retrievedAt: seed.retrieval === "retrieved" ? addMinutes(received, 1.5) : null,
      method: seed.retrievalMethod ?? "none",
      paragraphs,
      wordCount: wordCount(paragraphs),
      redactionCount: seed.redactions ?? 0,
      authors: seed.authors ?? [],
      imageCount: seed.images ?? 0,
      error: seed.retrievalError ?? null,
    },
    pipeline: buildPipeline(seed, received),
    extractionRuns: runs,
    linkedIncidents: INCIDENTS.filter((i) => linkedIncidentIds.includes(i.id)).map((i) => ({
      id: i.id,
      referenceCode: i.ref,
      title: i.title,
    })),
  };
}

/* ---------------------------------------------------------------- blackspots */

function buildBlackspots(): Blackspot[] {
  return BLACKSPOT_SEEDS.map((b) => {
    const nearby = INCIDENTS.filter(
      (i) => i.point && haversineKm(i.point, b.point) <= 25,
    ).length;
    return { ...b, synthetic: true, dataSourceName: BLACKSPOT_DATA_SOURCE, nearbyIncidentCount: nearby };
  });
}

/* -------------------------------------------------------------- ingestion runs */

function buildRuns(articles: SourceItemDetail[], rand: () => number): IngestionRun[] {
  const runs: IngestionRun[] = [];
  const windowEnd = DEMO_NOW.getTime();

  for (const source of SOURCES) {
    const interval = source.pollIntervalSeconds * 1000;
    const isPaused = !source.enabled;
    const lastStart = isPaused ? new Date(cat("2026-11-02 11:00")).getTime() : windowEnd - 40_000;
    const count = isPaused ? 12 : 40;
    const mine = articles.filter((a) => a.sourceId === source.id);

    for (let n = 0; n < count; n++) {
      const start = lastStart - n * interval;
      const startedAt = new Date(start).toISOString();
      const duration = Math.round(1800 + rand() * 4200);
      const completedAt = new Date(start + duration).toISOString();
      const inserted = mine.filter((a) => {
        const t = new Date(a.receivedAt).getTime();
        return t > start - interval && t <= start;
      }).length;
      const fetched = Math.round(12 + rand() * 14);

      let status: IngestionRun["status"] = "succeeded";
      let errorCount = 0;
      let errorMessage: string | null = null;
      if (source.id === "src-masvingo") {
        status = "failed";
        errorCount = 1;
        errorMessage = "HTTP 404 Not Found for the feed URL. The publisher may have moved its feed.";
      } else if (source.id === "src-eastern" && n % 4 === 1) {
        status = "failed";
        errorCount = 1;
        errorMessage = "Read timed out after 20 seconds.";
      } else if (source.id === "src-eastern" && n % 7 === 3) {
        status = "partial";
        errorCount = 2;
        errorMessage = "2 of 18 entries could not be parsed.";
      }

      const failed = status === "failed";
      runs.push({
        id: `ing-${source.id}-${String(n).padStart(3, "0")}`,
        sourceId: source.id,
        sourceName: source.name,
        startedAt,
        completedAt,
        status,
        fetchedCount: failed ? 0 : fetched,
        insertedCount: failed ? 0 : inserted,
        duplicateCount: failed ? 0 : Math.max(0, fetched - inserted),
        errorCount,
        errorMessage,
        trigger: "scheduled",
      });
    }
  }
  return runs.sort((a, b) => b.startedAt.localeCompare(a.startedAt));
}

function summariseSources(runs: IngestionRun[], articles: SourceItemDetail[]): SourceSummary[] {
  return SOURCES.map((s) => {
    const mine = runs.filter((r) => r.sourceId === s.id); // newest first
    const lastOk = mine.find((r) => r.status === "succeeded" || r.status === "partial");
    const recent = mine.slice(0, 8);
    const failures = recent.filter((r) => r.status === "failed").length;
    let connection: ConnectionStatus = "healthy";
    if (!s.enabled) connection = "disabled";
    else if (recent.length === 0) connection = "untested";
    else if (failures === recent.length) connection = "failing";
    else if (failures > 0 || recent.some((r) => r.status === "partial")) connection = "degraded";
    return {
      ...s,
      lastPollAt: mine[0]?.startedAt ?? null,
      lastSuccessfulPollAt: lastOk?.startedAt ?? null,
      articlesDiscovered: articles.filter((a) => a.sourceId === s.id).length,
      errorCount: mine.filter((r) => r.status === "failed").length,
      connectionStatus: connection,
      lastError: mine.find((r) => r.errorMessage)?.errorMessage ?? null,
    };
  });
}

/* ---------------------------------------------------------------- processing */

function buildJobs(articles: SourceItemDetail[], runs: IngestionRun[], rand: () => number): ProcessingJob[] {
  const jobs: ProcessingJob[] = runs.map((r) => ({
    id: `job-poll-${r.id}`,
    kind: "rss_poll",
    status: r.status === "running" ? "running" : r.status,
    sourceId: r.sourceId,
    sourceName: r.sourceName,
    sourceItemId: null,
    subject: `Poll of ${r.sourceName}`,
    startedAt: r.startedAt,
    durationMs: r.completedAt ? new Date(r.completedAt).getTime() - new Date(r.startedAt).getTime() : null,
    summary:
      r.status === "failed"
        ? "Feed could not be read."
        : `Fetched ${r.fetchedCount}, ${r.insertedCount} new, ${r.duplicateCount} already known.`,
    errorMessage: r.errorMessage,
    retryCount: 0,
    retryable: r.status === "failed",
    ingestionRunId: r.id,
  }));

  for (const a of articles) {
    const base = {
      sourceId: a.sourceId,
      sourceName: a.publisherName,
      sourceItemId: a.id,
      subject: a.titleRedacted,
      ingestionRunId: a.ingestionRunId,
    };
    if (a.screening) {
      jobs.push({
        ...base,
        id: `job-screen-${a.id}`,
        kind: "keyword_screening",
        status: "succeeded",
        startedAt: a.screening.screenedAt,
        durationMs: Math.round(20 + rand() * 60),
        summary: `Score ${a.screening.score.toFixed(2)}, ${a.screening.decision === "relevant" ? "relevant" : "not relevant"}.`,
        errorMessage: null,
        retryCount: 0,
        retryable: false,
      });
    } else {
      jobs.push({
        ...base,
        id: `job-screen-${a.id}`,
        kind: "keyword_screening",
        status: "pending",
        startedAt: a.receivedAt,
        durationMs: null,
        summary: "Waiting for the next screening pass.",
        errorMessage: null,
        retryCount: 0,
        retryable: false,
      });
    }

    if (a.screening?.decision === "relevant") {
      const retrievalStage = a.pipeline.find((p) => p.id === "full_text_retrieval");
      jobs.push({
        ...base,
        id: `job-fetch-${a.id}`,
        kind: "article_retrieval",
        status:
          a.retrievalStatus === "retrieved" ? "succeeded" : a.retrievalStatus === "failed" ? "failed" : "pending",
        startedAt: retrievalStage?.at ?? addMinutes(a.receivedAt, 1),
        durationMs: a.retrievalStatus === "pending" ? null : Math.round(700 + rand() * 2600),
        summary:
          a.retrievalStatus === "retrieved"
            ? `Retrieved ${a.content.wordCount} words (${a.content.method}).`
            : a.retrievalStatus === "failed"
              ? "Publisher refused the request."
              : "Queued.",
        errorMessage: a.content.error,
        retryCount: a.retrievalStatus === "failed" ? 2 : 0,
        retryable: a.retrievalStatus === "failed",
      });
    }

    const run = a.extractionRuns[a.extractionRuns.length - 1];
    if (run) {
      jobs.push({
        ...base,
        id: `job-extract-${a.id}`,
        kind: "ai_extraction",
        status: run.status === "pending" ? "running" : run.status,
        startedAt: run.createdAt,
        durationMs: run.durationMs,
        summary:
          run.status === "succeeded"
            ? `${run.events.length} event${run.events.length === 1 ? "" : "s"} extracted at ${Math.round((run.confidence ?? 0) * 100)}% model confidence.`
            : run.status === "failed"
              ? "Output failed schema validation."
              : "Model is processing the article.",
        errorMessage: run.errorMessage,
        retryCount: a.extractionRuns.length - 1,
        retryable: run.status === "failed",
      });
    }
  }
  return jobs.sort((x, y) => y.startedAt.localeCompare(x.startedAt));
}

/* ------------------------------------------------------------------ incidents */

function buildIncidentData(articles: SourceItemDetail[]) {
  const blackspots = buildBlackspots();
  const reviews: EditorialReview[] = REVIEWS.map((r) => ({
    id: r.id,
    incidentId: r.incidentId,
    bulletinVersionId: r.bulletinId,
    reviewerId: userId(r.by),
    reviewerName: userName(r.by),
    decision: r.decision,
    notes: r.notes,
    reviewedAt: cat(r.atCat),
  }));

  const bulletins: BulletinVersion[] = BULLETINS.map((b) => ({
    id: b.id,
    incidentId: b.incidentId,
    versionNumber: b.version,
    headline: b.headline,
    body: b.body,
    createdBy: userId(b.by),
    createdByName: b.by === "ai" ? `${AI_ACTOR.name} (draft)` : userName(b.by),
    createdAt: cat(b.atCat),
  }));

  const evidence: IncidentEvidence[] = [];
  const blackspotMatches: MockDb["blackspotMatches"] = {};
  const incidents: Incident[] = INCIDENTS.map((seed) => {
    const links = seed.evidence.map((e, idx): IncidentEvidence => {
      const article = articles.find((a) => a.id === e.articleId)!;
      const run = article.extractionRuns[0];
      const ev = run?.events.find((x) => x.id === e.eventId);
      return {
        id: `evd-${seed.id}-${idx + 1}`,
        incidentId: seed.id,
        sourceItemId: article.id,
        role: e.role,
        articleTitle: article.titleRedacted,
        publisherName: article.publisherName,
        publishedAt: article.publishedAt,
        canonicalUrl: article.canonicalUrl,
        snippet: ev?.evidenceSnippets[0]?.text ?? null,
        extractionRunId: run?.id ?? null,
        extractedEventId: e.eventId,
      };
    });
    evidence.push(...links);

    const point = seed.point ? { ...seed.point, synthetic: true } : null;
    const matches = point
      ? blackspots
          .map((b) => ({ b, d: haversineKm(point, b.point) }))
          .filter((x) => x.d <= BLACKSPOT_MATCH_KM)
          .sort((x, y) => x.d - y.d)
          .map((x) => ({ blackspotId: x.b.id, code: x.b.code, name: x.b.name, distanceKm: Math.round(x.d * 10) / 10 }))
      : [];
    blackspotMatches[seed.id] = matches;

    const created = cat(seed.createdCat);
    return {
      id: seed.id,
      referenceCode: seed.ref,
      title: seed.title,
      incidentType: seed.type,
      severity: seed.severity,
      locationText: seed.locationText,
      roadName: seed.roadName,
      province: seed.province,
      point,
      occurredAt: seed.occurredCat ? cat(seed.occurredCat) : null,
      occurredAtNote: seed.occurredNote,
      credibilityScore: seed.credibility,
      credibilityRationale: seed.credibilityRationale,
      geographicRiskScore: seed.risk,
      riskLevel: riskLevelFromScore(seed.risk),
      reviewPriority: seed.priority,
      status: seed.status,
      reviewState: deriveReviewState(
        seed.status,
        reviews.filter((r) => r.incidentId === seed.id),
      ),
      verification: deriveVerification(seed.status, links),
      summary: seed.summary,
      vehicles: seed.vehicles,
      trafficImpact: seed.traffic,
      missingInformation: seed.missing,
      sourceCount: links.filter((l) => l.role === "primary" || l.role === "corroborating").length,
      createdAt: created,
      updatedAt: created,
      synthetic: true,
    };
  });

  // Alerts: approval and delivery stay separate. Each channel records its own attempts.
  const alerts: PublicAlert[] = ALERTS.map((a) => {
    const incident = incidents.find((i) => i.id === a.incidentId)!;
    const bulletin = bulletins.find((b) => b.id === a.bulletinId)!;
    const review = reviews.find((r) => r.id === a.reviewId)!;
    const channels: ChannelDelivery[] = a.channels.map((c) => ({
      channel: c.channel,
      status: c.status,
      maxAttempts: 3,
      attempts: c.attempts.map((t, i) => ({
        id: `att-${a.id}-${c.channel}-${i + 1}`,
        attemptNumber: i + 1,
        status: t.ok ? "succeeded" : "failed",
        attemptedAt: cat(t.atCat),
        error: t.error ?? null,
      })),
      lastError: c.attempts.filter((t) => !t.ok).at(-1)?.error ?? null,
    }));
    return {
      id: a.id,
      reference: a.reference,
      incidentId: incident.id,
      incidentReference: incident.referenceCode,
      incidentType: incident.incidentType,
      locationText: incident.locationText,
      bulletinVersionId: bulletin.id,
      bulletinVersionNumber: bulletin.versionNumber,
      headline: bulletin.headline,
      body: bulletin.body,
      approvalReviewId: review.id,
      approvedByName: review.reviewerName,
      approvedAt: review.reviewedAt,
      status: "published",
      publishedAt: cat(a.publishedCat),
      publicationState: deriveAlertState("published", channels),
      channels,
      synthetic: true,
    };
  });

  // Audit trail (append-only in the real system).
  const audit: AuditEvent[] = [];
  const push = (
    incidentId: string,
    at: string,
    actorKind: AuditEvent["actorKind"],
    actorName: string,
    action: string,
    summary: string,
  ) =>
    audit.push({
      id: `aud-${incidentId}-${audit.length}`,
      occurredAt: at,
      actorKind,
      actorName,
      action,
      summary,
      entryRef: entryRef(`${incidentId}-${at}-${action}`),
      entityType: "incident",
      entityId: incidentId,
    });

  for (const seed of INCIDENTS) {
    const primary = seed.evidence[0];
    const article = articles.find((a) => a.id === primary.articleId)!;
    const run = article.extractionRuns[0];
    const m = blackspotMatches[seed.id];
    push(seed.id, article.receivedAt, "system", SYSTEM_ACTOR.name, "article_received", `Article received from ${article.publisherName}`);
    push(
      seed.id,
      addMinutes(article.receivedAt, 5),
      "ai",
      AI_ACTOR.name,
      "extraction_completed",
      `AI extraction completed at ${Math.round((run?.confidence ?? 0) * 100)}% confidence (suggestion only)`,
    );
    push(
      seed.id,
      addMinutes(article.receivedAt, 5.5),
      "ai",
      AI_ACTOR.name,
      "location_compared",
      m.length > 0
        ? `Location compared with demo blackspots: matched ${m[0].code}`
        : "Location compared with demo blackspots: no match within 10 km",
    );
    push(
      seed.id,
      cat(seed.createdCat),
      "system",
      SYSTEM_ACTOR.name,
      "queued",
      `Placed in review queue with suggested priority ${seed.priority.charAt(0).toUpperCase()}${seed.priority.slice(1)}`,
    );
    if (seed.openedCat) {
      push(
        seed.id,
        cat(seed.openedCat),
        "human",
        seed.id === "inc-0405" || seed.id === "inc-0413" ? OTHER_REVIEWERS[0].name : DEMO_USER.name,
        "opened_for_review",
        `Opened for review`,
      );
    }
    for (const r of reviews.filter((x) => x.incidentId === seed.id)) {
      const label = r.decision === "approved" ? "Approved" : r.decision === "rejected" ? "Rejected" : "Changes requested";
      push(seed.id, r.reviewedAt, "human", r.reviewerName, `decision_${r.decision}`, `${label} by ${r.reviewerName}`);
    }
    for (const a of alerts.filter((x) => x.incidentId === seed.id)) {
      if (a.publishedAt) {
        push(seed.id, a.publishedAt, "system", SYSTEM_ACTOR.name, "alert_published", `Alert ${a.reference} sent to delivery channels`);
      }
    }
  }
  audit.sort((x, y) => x.occurredAt.localeCompare(y.occurredAt));

  return { incidents, evidence, bulletins, reviews, alerts, blackspots, blackspotMatches, audit };
}

/* --------------------------------------------------------------------- build */

export function buildMockDb(): MockDb {
  const rand = seeded(20261103);
  const articles = ARTICLES.map((a) => buildArticle(a, rand));
  const ingestionRuns = buildRuns(articles, rand);
  const sources = summariseSources(ingestionRuns, articles);
  const jobs = buildJobs(articles, ingestionRuns, rand);
  const rest = buildIncidentData(articles);

  return { sources, ingestionRuns, articles, jobs, ...rest };
}
