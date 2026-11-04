import type {
  AlertStatus,
  AttemptStatus,
  ChannelKind,
  OutboxStatus,
  ReviewDecision,
} from "./common";
import type { ExtractedEvent } from "./ingestion";
import type { IncidentDetail } from "./incidents";

/** Mirrors `bulletin_versions`: immutable. An edit is always a new version. */
export interface BulletinVersion {
  id: string;
  incidentId: string;
  versionNumber: number;
  headline: string;
  body: string;
  createdBy: string;
  createdByName: string;
  createdAt: string;
}

/** Mirrors `editorial_reviews`: append-only human decisions. */
export interface EditorialReview {
  id: string;
  incidentId: string;
  bulletinVersionId: string | null;
  reviewerId: string;
  reviewerName: string;
  decision: ReviewDecision;
  notes: string | null;
  reviewedAt: string;
}

/**
 * Derived queue state for the Review Queue. Built from the incident status and
 * the latest human decision, not stored separately.
 */
export type ReviewState = "pending" | "needs_changes" | "approved" | "rejected";

export type AuditActorKind = "system" | "ai" | "human";

/** Append-only audit trail entry. */
export interface AuditEvent {
  id: string;
  occurredAt: string;
  actorKind: AuditActorKind;
  actorName: string;
  action: string;
  summary: string;
  /** Short entry reference, e.g. a41f. */
  entryRef: string;
  entityType: "source_item" | "incident" | "bulletin" | "alert";
  entityId: string;
}

export interface ReviewQueueItem {
  incidentId: string;
  referenceCode: string;
  title: string;
  incidentType: IncidentDetail["incidentType"];
  locationText: string | null;
  priority: IncidentDetail["reviewPriority"];
  state: ReviewState;
  sourceCount: number;
  missingInformationCount: number;
  riskLevel: IncidentDetail["riskLevel"];
  extractionConfidence: number | null;
  receivedAt: string;
  assignedTo: string | null;
  latestBulletinVersion: number | null;
}

export interface ReviewWorkspace {
  incident: IncidentDetail;
  state: ReviewState;
  bulletins: BulletinVersion[];
  reviews: EditorialReview[];
  history: AuditEvent[];
  /** Redacted evidence text, one block per linked article. */
  evidenceText: { sourceItemId: string; articleTitle: string; publisherName: string; paragraphs: string[] }[];
  /** The AI-extracted event behind the primary evidence, if any. A suggestion, not a fact. */
  primaryEvent: ExtractedEvent | null;
  /** Internal editorial notes (never published). Latest saved draft notes. */
  notes: string;
  /** True when an editor may record a decision (role-gated server-side in api mode). */
  canDecide: boolean;
}

/** Mirrors `notification_outbox` attempts. */
export interface DeliveryAttempt {
  id: string;
  attemptNumber: number;
  status: AttemptStatus;
  attemptedAt: string;
  error: string | null;
}

export interface ChannelDelivery {
  channel: ChannelKind;
  status: OutboxStatus;
  maxAttempts: number;
  attempts: DeliveryAttempt[];
  lastError: string | null;
}

/**
 * Derived display state. Approval and distribution are separate facts:
 * an approved bulletin has not necessarily reached anyone.
 */
export type AlertPublicationState =
  | "approved_not_published"
  | "publication_pending"
  | "published"
  | "delivery_failed"
  | "withdrawn";

/** Mirrors `public_alerts` with its approval trail. */
export interface PublicAlert {
  id: string;
  reference: string;
  incidentId: string;
  incidentReference: string;
  incidentType: IncidentDetail["incidentType"];
  locationText: string | null;
  bulletinVersionId: string;
  bulletinVersionNumber: number;
  headline: string;
  body: string;
  approvalReviewId: string;
  approvedByName: string;
  approvedAt: string;
  status: AlertStatus;
  publishedAt: string | null;
  publicationState: AlertPublicationState;
  channels: ChannelDelivery[];
  synthetic?: boolean;
}
