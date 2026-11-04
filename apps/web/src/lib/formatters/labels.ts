import type {
  AlertPublicationState,
  ArticleWorkflowState,
  ChannelKind,
  ConnectionStatus,
  EvidenceRole,
  ExtractionStatus,
  IncidentStatus,
  IncidentType,
  OutboxStatus,
  PipelineStageId,
  ProcessingJobKind,
  ProcessingJobStatus,
  ReviewPriority,
  ReviewState,
  RetrievalMethod,
  RetrievalStatus,
  RiskLevel,
  Severity,
  SourceKind,
  VerificationState,
  VerificationTier,
  KeywordGroup,
} from "@/types";
import type { CredibilityLevel } from "@/lib/domain/derive";

/** Plain-language names. Sentence case, and the same word everywhere. */

export const INCIDENT_TYPE_LABEL: Record<IncidentType, string> = {
  collision: "Collision",
  pedestrian_strike: "Pedestrian struck",
  rollover: "Rollover",
  vehicle_fire: "Vehicle fire",
  breakdown: "Breakdown",
  road_hazard: "Road hazard",
  road_closure: "Road closure",
  traffic_disruption: "Traffic disruption",
  other: "Other",
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  unknown: "Unknown",
  minor: "Minor",
  serious: "Serious",
  fatal: "Fatal",
};

export const PRIORITY_LABEL: Record<ReviewPriority, string> = {
  low: "Low",
  normal: "Normal",
  high: "High",
  urgent: "Urgent",
};

export const REVIEW_STATE_LABEL: Record<ReviewState, string> = {
  pending: "Pending review",
  needs_changes: "Needs changes",
  approved: "Approved",
  rejected: "Rejected",
};

export const INCIDENT_STATUS_LABEL: Record<IncidentStatus, string> = {
  candidate: "Candidate",
  under_review: "Under review",
  approved: "Approved",
  rejected: "Rejected",
  published: "Published",
  archived: "Archived",
};

export const VERIFICATION_LABEL: Record<VerificationState, string> = {
  unverified: "Unverified",
  single_source: "Single source",
  corroborated: "Corroborated by 2+ sources",
  editor_confirmed: "Wording approved by an editor",
};

/** Compact wording for table cells. */
export const VERIFICATION_SHORT_LABEL: Record<VerificationState, string> = {
  unverified: "Unverified",
  single_source: "Single source",
  corroborated: "2+ sources",
  editor_confirmed: "Editor-approved",
};

export const WORKFLOW_LABEL: Record<ArticleWorkflowState, string> = {
  new: "New",
  filtered: "Filtered out",
  relevant: "Relevant",
  awaiting_full_text: "Awaiting full text",
  full_text_retrieved: "Full text retrieved",
  extraction_pending: "Extraction pending",
  processed: "Processed",
  failed: "Failed",
};

export const RETRIEVAL_LABEL: Record<RetrievalStatus, string> = {
  retrieved: "Retrieved",
  pending: "Pending",
  failed: "Failed",
  skipped: "Skipped",
};

export const EXTRACTION_LABEL: Record<ExtractionStatus | "not_started", string> = {
  not_started: "Not started",
  pending: "Pending",
  succeeded: "Extracted",
  failed: "Failed",
};

export const ALERT_STATE_LABEL: Record<AlertPublicationState, string> = {
  approved_not_published: "Approved, not yet sent",
  publication_pending: "Publication pending",
  published: "Published",
  delivery_failed: "Delivery failed",
  withdrawn: "Withdrawn",
};

export const CHANNEL_LABEL: Record<ChannelKind, string> = {
  web: "Public map and API",
  sms: "SMS",
  whatsapp: "WhatsApp",
  email: "Email",
  webhook: "Webhook",
};

export const OUTBOX_LABEL: Record<OutboxStatus, string> = {
  pending: "Pending",
  sending: "Sending",
  sent: "Delivered",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const JOB_KIND_LABEL: Record<ProcessingJobKind, string> = {
  rss_poll: "RSS poll",
  keyword_screening: "Keyword screening",
  article_retrieval: "Article retrieval",
  ai_extraction: "AI extraction",
};

export const JOB_STATUS_LABEL: Record<ProcessingJobStatus, string> = {
  succeeded: "Succeeded",
  failed: "Failed",
  running: "Running",
  pending: "Queued",
  partial: "Partial",
  skipped: "Skipped",
};

export const CONNECTION_LABEL: Record<ConnectionStatus, string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  failing: "Failing",
  disabled: "Disabled",
  untested: "Not tested",
};

export const STAGE_LABEL: Record<PipelineStageId, string> = {
  rss_discovered: "RSS discovered",
  keyword_screening: "Keyword screening",
  full_text_retrieval: "Full article retrieval",
  content_extraction: "Content extraction",
  privacy_protection: "Privacy protection",
  ai_processing: "AI processing",
  schema_validation: "Schema validation",
  incident_candidate: "Incident candidate created",
};

export const TIER_LABEL: Record<VerificationTier, string> = {
  official: "Official",
  established_media: "Established media",
  community: "Community",
  unverified: "Unverified",
};

export const SOURCE_KIND_LABEL: Record<SourceKind, string> = {
  rss: "RSS feed",
  official: "Official channel",
  whatsapp: "WhatsApp",
  social: "Social media",
  manual: "Manual report",
};

export const RISK_LABEL: Record<RiskLevel, string> = {
  low: "Low",
  medium: "Elevated",
  high: "High",
  critical: "Critical",
};

export const CREDIBILITY_LABEL: Record<CredibilityLevel, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
};

export const EVIDENCE_ROLE_LABEL: Record<EvidenceRole, string> = {
  primary: "Primary source",
  corroborating: "Corroborating",
  contradicting: "Contradicting",
  context: "Context",
};

export const RETRIEVAL_METHOD_LABEL: Record<RetrievalMethod, string> = {
  rss_full_content: "Full text in the RSS feed",
  page_fetch: "Fetched from the article page",
  homepage_scrape: "Read from the publisher homepage",
  none: "Not retrieved",
};

export const KEYWORD_GROUP_LABEL: Record<KeywordGroup, string> = {
  incident: "Incident",
  vehicle: "Vehicle",
  road: "Road",
  location: "Place",
  impact: "Impact",
};

export const ACCURACY_LABEL = {
  exact: "Exact position",
  road_segment: "Along the road",
  town: "Town level",
  approximate: "Approximate",
} as const;
