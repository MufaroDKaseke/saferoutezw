import type {
  AlertPublicationState,
  AlertStatus,
  ArticleWorkflowState,
  ChannelDelivery,
  EditorialReview,
  EvidenceRole,
  IncidentStatus,
  ReviewDecision,
  ReviewState,
  RetrievalStatus,
  RiskLevel,
  VerificationState,
  KeywordScreeningResult,
  ExtractionStatus,
} from "@/types";

/**
 * Pure derivation rules. They encode the product's central distinctions:
 *   article ≠ incident, relevance ≠ verification, AI extraction ≠ approval,
 *   approval ≠ distribution, blackspot proximity ≠ confirmation.
 */

/** Keyword relevance threshold used by the demo ruleset. */
export const RELEVANCE_THRESHOLD = 0.4;

/* ------------------------------------------------------------------ scores */

export function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n));
}

/** Geographic-risk bands. Context only; never evidence an incident happened. */
export function riskLevelFromScore(score: number | null | undefined): RiskLevel | null {
  if (score == null) return null;
  if (score < 0.35) return "low";
  if (score < 0.6) return "medium";
  if (score < 0.85) return "high";
  return "critical";
}

export type CredibilityLevel = "low" | "moderate" | "high";

/** Credibility is a decision aid about how well the evidence supports the event. */
export function credibilityLevel(score: number | null | undefined): CredibilityLevel | null {
  if (score == null) return null;
  if (score < 0.4) return "low";
  if (score < 0.7) return "moderate";
  return "high";
}

/** Number of filled segments (1 to 5) in the segmented meters. */
export function scoreSegments(score: number | null | undefined): number {
  if (score == null) return 0;
  return Math.min(5, Math.max(1, Math.floor(clamp01(score) * 5)));
}

export type ConfidenceBand = "high" | "medium" | "low";

/** AI extraction confidence band: how well fields were extracted, not whether the event is real. */
export function confidenceBand(confidence: number | null | undefined): ConfidenceBand | null {
  if (confidence == null) return null;
  if (confidence >= 0.8) return "high";
  if (confidence >= 0.6) return "medium";
  return "low";
}

/* ----------------------------------------------------------------- reviews */

/**
 * Queue state from the incident status and the latest *human* decision. Only a
 * recorded decision moves an incident out of `pending`.
 */
export function deriveReviewState(
  status: IncidentStatus,
  reviews: Pick<EditorialReview, "decision" | "reviewedAt">[],
): ReviewState {
  if (status === "rejected") return "rejected";
  if (status === "approved" || status === "published") return "approved";
  const latest = [...reviews].sort((a, b) => b.reviewedAt.localeCompare(a.reviewedAt))[0];
  if (latest?.decision === "needs_changes") return "needs_changes";
  return "pending";
}

export function decisionToIncidentStatus(decision: ReviewDecision): IncidentStatus {
  switch (decision) {
    case "approved":
      return "approved";
    case "rejected":
      return "rejected";
    case "needs_changes":
      return "under_review";
  }
}

/** Corroboration is counted from independent supporting articles only. */
export function deriveVerification(
  status: IncidentStatus,
  evidence: { role: EvidenceRole }[],
): VerificationState {
  if (status === "approved" || status === "published") return "editor_confirmed";
  if (status === "rejected") return "unverified";
  const supporting = evidence.filter((e) => e.role === "primary" || e.role === "corroborating").length;
  if (supporting >= 2) return "corroborated";
  if (supporting === 1) return "single_source";
  return "unverified";
}

/* ------------------------------------------------------------------ alerts */

/**
 * Approval and distribution are separate facts. An approved bulletin that has
 * not been sent is `approved_not_published`, and a published alert with a failed
 * channel is `delivery_failed`, never plain "published".
 */
export function deriveAlertState(
  status: AlertStatus,
  channels: Pick<ChannelDelivery, "status">[],
): AlertPublicationState {
  if (status === "withdrawn") return "withdrawn";
  if (channels.some((c) => c.status === "failed")) return "delivery_failed";
  if (status === "published") {
    return channels.some((c) => c.status === "pending" || c.status === "sending")
      ? "publication_pending"
      : "published";
  }
  return channels.some((c) => c.status === "pending" || c.status === "sending")
    ? "publication_pending"
    : "approved_not_published";
}

/* ---------------------------------------------------------------- articles */

export interface WorkflowInputs {
  screening: Pick<KeywordScreeningResult, "decision"> | null;
  retrieval: RetrievalStatus;
  extraction: ExtractionStatus | "not_started";
}

/** The article-level label shown in the News Monitor. */
export function deriveWorkflowState({ screening, retrieval, extraction }: WorkflowInputs): ArticleWorkflowState {
  if (!screening) return "new";
  if (screening.decision === "not_relevant") return "filtered";
  if (retrieval === "failed" || extraction === "failed") return "failed";
  if (retrieval === "pending") return "awaiting_full_text";
  if (retrieval === "retrieved") {
    if (extraction === "succeeded") return "processed";
    if (extraction === "pending") return "extraction_pending";
    return "full_text_retrieved";
  }
  return "relevant";
}

/** Workflow states that mean a person may want to look at the article. */
export const ATTENTION_STATES: ArticleWorkflowState[] = ["failed"];
