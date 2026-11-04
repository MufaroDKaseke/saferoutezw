import { NotFoundError, PermissionError, ValidationError } from "@/lib/api/errors";
import type { ActionResult, SourceInput, SourceTestResult } from "@/lib/api/types";
import { deriveAlertState, deriveVerification } from "@/lib/domain/derive";
import { REVIEWER_ROLES } from "@/types";
import type {
  AuditEvent,
  BulletinVersion,
  ChannelDelivery,
  ChannelKind,
  EditorialReview,
  Incident,
  IngestionRun,
  PublicAlert,
  SourceItemDetail,
  SourceSummary,
} from "@/types";
import { DEMO_USER, SYSTEM_ACTOR } from "./data/people-sources";
import { demoNow, getDb, update } from "./store";

/**
 * Simulated actions. They change only the in-memory demo state and every result
 * is flagged `simulated: true`. Nothing reaches PostgreSQL, WhatsApp, SMS or any
 * public channel. Real approvals must be validated by the FastAPI backend and
 * enforced by the database triggers.
 */

let counter = 0;
const nextId = (prefix: string) => `${prefix}-sim-${++counter}-${Date.now().toString(36)}`;

function simulated<T>(message: string, data?: T): ActionResult<T> {
  return { simulated: true, message, data };
}

function assertCanDecide() {
  // A client-side check is a convenience only. The backend must enforce this.
  if (!REVIEWER_ROLES.includes(DEMO_USER.role)) throw new PermissionError();
}

function entryRef(): string {
  return Math.floor(Math.random() * 0xffff)
    .toString(16)
    .padStart(4, "0");
}

function audit(
  incidentId: string,
  actorKind: AuditEvent["actorKind"],
  actorName: string,
  action: string,
  summary: string,
  entityType: AuditEvent["entityType"] = "incident",
): AuditEvent {
  return {
    id: nextId("aud"),
    occurredAt: demoNow(),
    actorKind,
    actorName,
    action,
    summary: `${summary} (simulated)`,
    entryRef: entryRef(),
    entityType,
    entityId: incidentId,
  };
}

function findIncident(id: string): Incident {
  const incident = getDb().incidents.find((i) => i.id === id);
  if (!incident) throw new NotFoundError("Incident");
  return incident;
}

function assertOpen(incident: Incident) {
  if (incident.reviewState === "approved" || incident.reviewState === "rejected") {
    throw new ValidationError("This incident already has a final decision.");
  }
}

function validateBulletin(headline: string, body: string) {
  if (!headline.trim()) throw new ValidationError("Add a headline before continuing.", "headline");
  if (!body.trim()) throw new ValidationError("Add the public summary before continuing.", "body");
}

/** Save a new bulletin version only when the text actually changed. */
function ensureBulletin(
  incidentId: string,
  headline: string,
  body: string,
): { bulletin: BulletinVersion; created: boolean } {
  const existing = getDb()
    .bulletins.filter((b) => b.incidentId === incidentId)
    .sort((a, b) => b.versionNumber - a.versionNumber);
  const latest = existing[0];
  if (latest && latest.headline === headline.trim() && latest.body === body.trim()) {
    return { bulletin: latest, created: false };
  }
  const bulletin: BulletinVersion = {
    id: nextId("bul"),
    incidentId,
    versionNumber: (latest?.versionNumber ?? 0) + 1,
    headline: headline.trim(),
    body: body.trim(),
    createdBy: DEMO_USER.id,
    createdByName: DEMO_USER.name,
    createdAt: demoNow(),
  };
  return { bulletin, created: true };
}

/* ------------------------------------------------------------ editorial */

export interface DraftInput {
  headline: string;
  body: string;
  notes?: string;
}

export function saveDraft(incidentId: string, input: DraftInput): ActionResult<{ versionNumber: number }> {
  assertCanDecide();
  const incident = findIncident(incidentId);
  assertOpen(incident);
  validateBulletin(input.headline, input.body);
  const db = getDb();
  const { bulletin, created } = ensureBulletin(incidentId, input.headline, input.body);
  const events: AuditEvent[] = [];
  if (created) {
    events.push(audit(incidentId, "human", DEMO_USER.name, "draft_saved", `Draft saved as bulletin version ${bulletin.versionNumber} by ${DEMO_USER.name}`, "bulletin"));
  }
  update(
    {
      bulletins: created ? [...db.bulletins, bulletin] : db.bulletins,
      audit: [...db.audit, ...events],
      incidents: db.incidents.map((i) =>
        i.id === incidentId
          ? { ...i, status: i.status === "candidate" ? "under_review" : i.status, updatedAt: demoNow() }
          : i,
      ),
    },
    { incidentId, text: input.notes ?? "" },
  );
  return simulated(
    created
      ? `Draft saved as version ${bulletin.versionNumber}. Demo only.`
      : "Notes saved. The bulletin text has not changed. Demo only.",
    { versionNumber: bulletin.versionNumber },
  );
}

export function requestChanges(incidentId: string, notes: string): ActionResult {
  assertCanDecide();
  const incident = findIncident(incidentId);
  assertOpen(incident);
  if (notes.trim().length < 5) {
    throw new ValidationError("Say what needs to change so the next editor can act on it.", "notes");
  }
  const db = getDb();
  const latest = db.bulletins
    .filter((b) => b.incidentId === incidentId)
    .sort((a, b) => b.versionNumber - a.versionNumber)[0];
  const review: EditorialReview = {
    id: nextId("rev"),
    incidentId,
    bulletinVersionId: latest?.id ?? null,
    reviewerId: DEMO_USER.id,
    reviewerName: DEMO_USER.name,
    decision: "needs_changes",
    notes: notes.trim(),
    reviewedAt: demoNow(),
  };
  update({
    reviews: [...db.reviews, review],
    audit: [...db.audit, audit(incidentId, "human", DEMO_USER.name, "decision_needs_changes", `Changes requested by ${DEMO_USER.name}`)],
    incidents: db.incidents.map((i) =>
      i.id === incidentId ? { ...i, status: "under_review", reviewState: "needs_changes", updatedAt: demoNow() } : i,
    ),
  });
  return simulated("Changes requested. Demo only.");
}

export function rejectIncident(incidentId: string, reason: string): ActionResult {
  assertCanDecide();
  const incident = findIncident(incidentId);
  assertOpen(incident);
  if (reason.trim().length < 10) {
    throw new ValidationError("Give a reason of at least 10 characters. It is kept in the review history.", "reason");
  }
  const db = getDb();
  const latest = db.bulletins
    .filter((b) => b.incidentId === incidentId)
    .sort((a, b) => b.versionNumber - a.versionNumber)[0];
  const review: EditorialReview = {
    id: nextId("rev"),
    incidentId,
    bulletinVersionId: latest?.id ?? null,
    reviewerId: DEMO_USER.id,
    reviewerName: DEMO_USER.name,
    decision: "rejected",
    notes: reason.trim(),
    reviewedAt: demoNow(),
  };
  update({
    reviews: [...db.reviews, review],
    audit: [...db.audit, audit(incidentId, "human", DEMO_USER.name, "decision_rejected", `Rejected by ${DEMO_USER.name}`)],
    incidents: db.incidents.map((i) =>
      i.id === incidentId
        ? { ...i, status: "rejected", reviewState: "rejected", verification: "unverified", updatedAt: demoNow() }
        : i,
    ),
  });
  return simulated("Rejected. The reason is saved in the review history. Demo only.");
}

export function approveIncident(
  incidentId: string,
  input: DraftInput,
): ActionResult<{ alertId: string; versionNumber: number }> {
  assertCanDecide();
  const incident = findIncident(incidentId);
  assertOpen(incident);
  validateBulletin(input.headline, input.body);

  const db = getDb();
  const { bulletin, created } = ensureBulletin(incidentId, input.headline, input.body);
  const review: EditorialReview = {
    id: nextId("rev"),
    incidentId,
    bulletinVersionId: bulletin.id,
    reviewerId: DEMO_USER.id,
    reviewerName: DEMO_USER.name,
    decision: "approved",
    notes: input.notes?.trim() || null,
    reviewedAt: demoNow(),
  };
  const evidence = db.evidence.filter((e) => e.incidentId === incidentId);
  const alert: PublicAlert = {
    id: nextId("alert"),
    reference: `A-${incident.referenceCode.replace(/^SR-/, "")}`,
    incidentId,
    incidentReference: incident.referenceCode,
    incidentType: incident.incidentType,
    locationText: incident.locationText,
    bulletinVersionId: bulletin.id,
    bulletinVersionNumber: bulletin.versionNumber,
    headline: bulletin.headline,
    body: bulletin.body,
    approvalReviewId: review.id,
    approvedByName: DEMO_USER.name,
    approvedAt: review.reviewedAt,
    // Approved, but not sent anywhere. Approval is not distribution.
    status: "ready",
    publishedAt: null,
    publicationState: "approved_not_published",
    channels: [],
    synthetic: true,
  };
  const events: AuditEvent[] = [];
  if (created) {
    events.push(audit(incidentId, "human", DEMO_USER.name, "draft_saved", `Bulletin version ${bulletin.versionNumber} saved by ${DEMO_USER.name}`, "bulletin"));
  }
  events.push(audit(incidentId, "human", DEMO_USER.name, "decision_approved", `Approved by ${DEMO_USER.name}. Bulletin version ${bulletin.versionNumber}`));

  update({
    bulletins: created ? [...db.bulletins, bulletin] : db.bulletins,
    reviews: [...db.reviews, review],
    alerts: [...db.alerts, alert],
    audit: [...db.audit, ...events],
    incidents: db.incidents.map((i) =>
      i.id === incidentId
        ? {
            ...i,
            status: "approved",
            reviewState: "approved",
            verification: deriveVerification("approved", evidence),
            updatedAt: demoNow(),
          }
        : i,
    ),
  });
  return simulated(
    `Approval recorded for bulletin version ${bulletin.versionNumber}. Nothing was published or sent.`,
    { alertId: alert.id, versionNumber: bulletin.versionNumber },
  );
}

/* --------------------------------------------------------------- alerts */

function patchAlert(id: string, fn: (a: PublicAlert) => PublicAlert): PublicAlert[] {
  const db = getDb();
  if (!db.alerts.some((a) => a.id === id)) throw new NotFoundError("Alert");
  return db.alerts.map((a) => (a.id === id ? fn(a) : a));
}

const ALL_CHANNELS: ChannelKind[] = ["whatsapp", "sms", "web"];

export function publishAlert(alertId: string): ActionResult {
  const db = getDb();
  const alert = db.alerts.find((a) => a.id === alertId);
  if (!alert) throw new NotFoundError("Alert");
  if (alert.status !== "ready") throw new ValidationError("Only an approved alert that is ready can be published.");
  const at = demoNow();
  const channels: ChannelDelivery[] = ALL_CHANNELS.map((channel) => ({
    channel,
    status: "sent",
    maxAttempts: 3,
    lastError: null,
    attempts: [{ id: nextId("att"), attemptNumber: 1, status: "succeeded", attemptedAt: at, error: null }],
  }));
  update({
    alerts: patchAlert(alertId, (a) => ({
      ...a,
      status: "published",
      publishedAt: at,
      channels,
      publicationState: deriveAlertState("published", channels),
    })),
    incidents: db.incidents.map((i) => (i.id === alert.incidentId ? { ...i, status: "published", updatedAt: at } : i)),
    audit: [...db.audit, audit(alert.incidentId, "system", SYSTEM_ACTOR.name, "alert_published", `Alert ${alert.reference} marked published to all channels`, "alert")],
  });
  return simulated("Marked as published in the demo. No message was sent to WhatsApp, SMS or any API.");
}

export function retryDelivery(alertId: string, channel: ChannelKind): ActionResult {
  const alert = getDb().alerts.find((a) => a.id === alertId);
  if (!alert) throw new NotFoundError("Alert");
  const target = alert.channels.find((c) => c.channel === channel);
  if (!target) throw new NotFoundError("Channel");
  if (target.status !== "failed") throw new ValidationError("Only a failed delivery can be retried.");
  if (target.attempts.length >= target.maxAttempts) {
    throw new ValidationError(`All ${target.maxAttempts} attempts have been used for this channel.`);
  }
  const at = demoNow();
  update({
    alerts: patchAlert(alertId, (a) => {
      const channels = a.channels.map((c) =>
        c.channel === channel
          ? {
              ...c,
              status: "sent" as const,
              lastError: null,
              attempts: [
                ...c.attempts,
                { id: nextId("att"), attemptNumber: c.attempts.length + 1, status: "succeeded" as const, attemptedAt: at, error: null },
              ],
            }
          : c,
      );
      return { ...a, channels, publicationState: deriveAlertState(a.status, channels) };
    }),
  });
  return simulated(`Simulated retry recorded for ${channel}. No message was sent.`);
}

/* ------------------------------------------------------ news / processing */

function retryArticleInternal(article: SourceItemDetail): SourceItemDetail {
  const note = "Retry queued (simulated). Nothing has been processed.";
  if (article.retrievalStatus === "failed") {
    return {
      ...article,
      retrievalStatus: "pending",
      workflowState: "awaiting_full_text",
      processingStatus: "pending",
      content: { ...article.content, retrievalStatus: "pending", error: null },
      pipeline: article.pipeline.map((p) =>
        p.id === "full_text_retrieval" ? { ...p, status: "pending", at: null, detail: note } : p,
      ),
    };
  }
  return {
    ...article,
    extractionStatus: "pending",
    workflowState: "extraction_pending",
    processingStatus: "processing",
    pipeline: article.pipeline.map((p) =>
      p.id === "schema_validation" || p.id === "ai_processing"
        ? { ...p, status: "pending", at: null, detail: p.id === "ai_processing" ? note : null }
        : p,
    ),
  };
}

export function retryArticle(articleId: string): ActionResult {
  const db = getDb();
  const article = db.articles.find((a) => a.id === articleId);
  if (!article) throw new NotFoundError("Article");
  if (article.workflowState !== "failed") throw new ValidationError("Only failed articles can be retried.");
  const kind = article.retrievalStatus === "failed" ? "article_retrieval" : "ai_extraction";
  update({
    articles: db.articles.map((a) => (a.id === articleId ? retryArticleInternal(a) : a)),
    jobs: db.jobs.map((j) =>
      j.sourceItemId === articleId && j.kind === kind
        ? {
            ...j,
            status: "pending",
            retryCount: j.retryCount + 1,
            summary: "Retry queued (simulated). Nothing has been processed.",
            errorMessage: null,
            retryable: false,
            simulated: true,
          }
        : j,
    ),
  });
  return simulated("Retry queued in the demo. No retrieval or AI call was made.");
}

export function retryJob(jobId: string): ActionResult {
  const db = getDb();
  const job = db.jobs.find((j) => j.id === jobId);
  if (!job) throw new NotFoundError("Job");
  if (!job.retryable) throw new ValidationError("This job cannot be retried.");
  if (job.sourceItemId) return retryArticle(job.sourceItemId);
  update({
    jobs: db.jobs.map((j) =>
      j.id === jobId
        ? { ...j, status: "pending", retryCount: j.retryCount + 1, summary: "Retry queued (simulated). No feed was fetched.", errorMessage: null, retryable: false, simulated: true }
        : j,
    ),
  });
  return simulated("Retry queued in the demo. No feed was fetched.");
}

/* -------------------------------------------------------------- sources */

function validateSource(input: SourceInput, ignoreId?: string) {
  const name = input.name.trim();
  if (!name) throw new ValidationError("Enter the publisher name.", "name");
  let url: URL;
  try {
    url = new URL(input.feedUrl.trim());
  } catch {
    throw new ValidationError("Enter a full feed URL, such as https://example.com/feed.", "feedUrl");
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw new ValidationError("The feed URL must start with http:// or https://.", "feedUrl");
  }
  if (!Number.isFinite(input.pollIntervalSeconds) || input.pollIntervalSeconds < 60) {
    throw new ValidationError("Polling every less than 60 seconds is not allowed.", "pollIntervalSeconds");
  }
  const others = getDb().sources.filter((s) => s.id !== ignoreId);
  if (others.some((s) => s.name.toLowerCase() === name.toLowerCase())) {
    throw new ValidationError("A source with this name already exists.", "name");
  }
  if (others.some((s) => s.feedUrl?.toLowerCase() === url.toString().toLowerCase())) {
    throw new ValidationError("This feed URL is already configured.", "feedUrl");
  }
}

export function createSource(input: SourceInput): ActionResult<SourceSummary> {
  validateSource(input);
  const source: SourceSummary = {
    id: nextId("src"),
    name: input.name.trim(),
    kind: "rss",
    feedUrl: new URL(input.feedUrl.trim()).toString(),
    enabled: true,
    pollIntervalSeconds: input.pollIntervalSeconds,
    verificationTier: input.verificationTier,
    rightsNotes: input.rightsNotes?.trim() || null,
    synthetic: true,
    lastPollAt: null,
    lastSuccessfulPollAt: null,
    articlesDiscovered: 0,
    errorCount: 0,
    connectionStatus: "untested",
    lastError: null,
  };
  update({ sources: [...getDb().sources, source] });
  return simulated("Feed added to the demo list. Nothing will be polled.", source);
}

export function updateSource(
  id: string,
  patch: Partial<SourceInput> & { enabled?: boolean },
): ActionResult<SourceSummary> {
  const db = getDb();
  const current = db.sources.find((s) => s.id === id);
  if (!current) throw new NotFoundError("Source");
  const merged: SourceInput = {
    name: patch.name ?? current.name,
    feedUrl: patch.feedUrl ?? current.feedUrl ?? "",
    pollIntervalSeconds: patch.pollIntervalSeconds ?? current.pollIntervalSeconds,
    verificationTier: patch.verificationTier ?? current.verificationTier,
    rightsNotes: patch.rightsNotes === undefined ? current.rightsNotes : patch.rightsNotes,
  };
  validateSource(merged, id);
  const enabled = patch.enabled ?? current.enabled;
  const next: SourceSummary = {
    ...current,
    name: merged.name.trim(),
    feedUrl: new URL(merged.feedUrl.trim()).toString(),
    pollIntervalSeconds: merged.pollIntervalSeconds,
    verificationTier: merged.verificationTier,
    rightsNotes: merged.rightsNotes?.trim() || null,
    enabled,
    connectionStatus: !enabled ? "disabled" : current.connectionStatus === "disabled" ? "untested" : current.connectionStatus,
  };
  update({ sources: db.sources.map((s) => (s.id === id ? next : s)) });
  return simulated(enabled === current.enabled ? "Source updated in the demo." : enabled ? "Source enabled in the demo." : "Source disabled in the demo.", next);
}

export function testSource(id: string): ActionResult<SourceTestResult> {
  const db = getDb();
  const source = db.sources.find((s) => s.id === id);
  if (!source) throw new NotFoundError("Source");
  // The demo never makes a network request. The outcome mirrors the source's recorded health.
  const result: SourceTestResult =
    source.connectionStatus === "failing"
      ? { ok: false, message: source.lastError ?? "The feed could not be read.", itemsFound: null }
      : source.connectionStatus === "disabled"
        ? { ok: false, message: "The source is disabled. Enable it before testing.", itemsFound: null }
        : { ok: true, message: "The feed looks reachable and readable.", itemsFound: 18 };
  if (source.connectionStatus === "untested" && result.ok) {
    update({ sources: db.sources.map((s) => (s.id === id ? { ...s, connectionStatus: "healthy" } : s)) });
  }
  return simulated("Simulated test. No network request was made.", result);
}

export function triggerPoll(id: string): ActionResult<IngestionRun> {
  const db = getDb();
  const source = db.sources.find((s) => s.id === id);
  if (!source) throw new NotFoundError("Source");
  if (!source.enabled) throw new ValidationError("Enable the source before polling it.");
  const at = demoNow();
  const run: IngestionRun = {
    id: nextId("ing"),
    sourceId: id,
    sourceName: source.name,
    startedAt: at,
    completedAt: at,
    status: "succeeded",
    fetchedCount: 0,
    insertedCount: 0,
    duplicateCount: 0,
    errorCount: 0,
    errorMessage: null,
    trigger: "manual",
    simulated: true,
  };
  update({
    ingestionRuns: [run, ...db.ingestionRuns],
    sources: db.sources.map((s) => (s.id === id ? { ...s, lastPollAt: at } : s)),
  });
  return simulated("Simulated poll recorded. No feed was fetched.", run);
}
