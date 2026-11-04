import type { NewsClassification } from "./intelligence";
import type {
  ExtractionStatus,
  IncidentType,
  IngestionStatus,
  ProcessingStatus,
  Severity,
  SourceKind,
  VerificationTier,
} from "./common";

/* ------------------------------------------------------------------ sources */

export type ConnectionStatus = "healthy" | "degraded" | "failing" | "disabled" | "untested";

/** Mirrors `sources`. */
export interface Source {
  id: string;
  name: string;
  kind: SourceKind;
  feedUrl: string | null;
  enabled: boolean;
  pollIntervalSeconds: number;
  verificationTier: VerificationTier;
  rightsNotes: string | null;
  /** Synthetic-data marker. Absent on real API responses. */
  synthetic?: boolean;
}

/** Source plus the health figures the Data Sources page needs (dedicated response type). */
export interface SourceSummary extends Source {
  lastPollAt: string | null;
  lastSuccessfulPollAt: string | null;
  articlesDiscovered: number;
  errorCount: number;
  connectionStatus: ConnectionStatus;
  lastError: string | null;
}

/** Mirrors `ingestion_runs`, plus a frontend-visible trigger. */
export interface IngestionRun {
  id: string;
  sourceId: string;
  sourceName: string;
  startedAt: string;
  completedAt: string | null;
  status: IngestionStatus;
  fetchedCount: number;
  insertedCount: number;
  duplicateCount: number;
  errorCount: number;
  errorMessage: string | null;
  trigger: "scheduled" | "manual";
  /** True when created by a demo action. Never set by a real backend. */
  simulated?: boolean;
}

/* ---------------------------------------------------------------- screening */

export type KeywordGroup = "incident" | "vehicle" | "road" | "location" | "impact";

export interface MatchedKeyword {
  term: string;
  group: KeywordGroup;
  occurrences: number;
}

/** Keyword relevance. A match is a reason to look, never proof an accident happened. */
export interface KeywordScreeningResult {
  /** 0..1 relevance score from the keyword ruleset. */
  /** Null when the backend does not score relevance (it only records a matched/not matched decision). */
  score: number | null;
  decision: "relevant" | "not_relevant";
  matchedKeywords: MatchedKeyword[];
  rulesetVersion: string | null;
  screenedAt: string | null;
}

/* ------------------------------------------------------------ article body */

export type RetrievalStatus = "retrieved" | "pending" | "failed" | "skipped";
export type RetrievalMethod = "rss_full_content" | "page_fetch" | "homepage_scrape" | "none";

/** The privacy-safe, readable article body. Raw HTML never reaches the browser. */
export interface ArticleContent {
  retrievalStatus: RetrievalStatus;
  retrievedAt: string | null;
  method: RetrievalMethod;
  /** Paragraphs of redacted plain text. */
  paragraphs: string[];
  wordCount: number;
  /** How many personal details were masked before storage. */
  redactionCount: number;
  authors: string[];
  imageCount: number;
  error: string | null;
}

/* ---------------------------------------------------------- pipeline stages */

export type PipelineStageId =
  | "rss_discovered"
  | "keyword_screening"
  | "full_text_retrieval"
  | "content_extraction"
  | "privacy_protection"
  | "ai_processing"
  | "schema_validation"
  | "incident_candidate";

export type StageStatus = "completed" | "pending" | "failed" | "skipped";

export interface PipelineStage {
  id: PipelineStageId;
  status: StageStatus;
  at: string | null;
  detail: string | null;
}

/**
 * Derived, article-level workflow label shown in the News Monitor. The backend
 * only persists `processing_status`; the finer stages are expected to arrive as
 * `source_metadata` or a future processing endpoint.
 */
export type ArticleWorkflowState =
  | "new"
  | "filtered"
  | "relevant"
  | "awaiting_full_text"
  | "full_text_retrieved"
  | "extraction_pending"
  | "processed"
  | "failed";

/* ------------------------------------------------------------ source items */

/** Mirrors `source_items`: one article or report, redacted. An article is NOT an incident. */
export interface SourceItem {
  id: string;
  sourceId: string;
  publisherName: string;
  sourceKind: SourceKind;
  ingestionRunId: string | null;
  externalId: string | null;
  canonicalUrl: string | null;
  titleRedacted: string;
  excerptRedacted: string | null;
  publishedAt: string | null;
  receivedAt: string;
  processingStatus: ProcessingStatus;
  workflowState: ArticleWorkflowState;
  /** Null until keyword screening has run (a brand-new article). */
  screening: KeywordScreeningResult | null;
  retrievalStatus: RetrievalStatus;
  extractionStatus: ExtractionStatus | "not_started";
  /** Incident candidates this article provides evidence for (an article may feed several). */
  linkedIncidentIds: string[];
  /** Transport-intelligence classification. Absent in demo data and for older records. */
  classification?: NewsClassification;
  /** Where the item came from, e.g. rss or a social platform. */
  sourcePlatform?: string;
  synthetic?: boolean;
}

/* -------------------------------------------------------------- extraction */

export interface EvidenceSnippet {
  field: string;
  text: string;
}

/** One event found in an article. An article can contain several. */
export interface ExtractedEvent {
  id: string;
  incidentType: IncidentType;
  locationText: string | null;
  roadName: string | null;
  kmPeg: string | null;
  occurredAtText: string | null;
  occurredAt: string | null;
  vehicles: string[];
  trafficImpact: string | null;
  /** Only populated when the article itself states it. */
  injuries: string | null;
  fatalities: string | null;
  suggestedSeverity: Severity;
  /** Model-reported confidence 0..1. Not proof the event occurred. */
  confidence: number;
  evidenceSnippets: EvidenceSnippet[];
  missingInformation: string[];
  linkedIncidentId: string | null;
}

/** Mirrors `extraction_runs`, expanded with the structured output. */
export interface ExtractionRun {
  id: string;
  sourceItemId: string;
  modelName: string;
  modelVersion: string | null;
  status: ExtractionStatus;
  createdAt: string;
  durationMs: number | null;
  confidence: number | null;
  classification: "road_incident" | "not_road_incident" | "uncertain" | null;
  events: ExtractedEvent[];
  schemaValidation: { passed: boolean; errors: string[] } | null;
  errorMessage: string | null;
}

export interface SourceItemDetail extends SourceItem {
  rssTitle: string;
  rssSummary: string | null;
  content: ArticleContent;
  pipeline: PipelineStage[];
  extractionRuns: ExtractionRun[];
  linkedIncidents: { id: string; referenceCode: string; title: string }[];
}

/* ------------------------------------------------------- processing activity */

export type ProcessingJobKind =
  | "rss_poll"
  | "keyword_screening"
  | "article_retrieval"
  | "ai_extraction";
export type ProcessingJobStatus = "succeeded" | "failed" | "running" | "pending" | "partial" | "skipped";

/** A single row in the Processing Activity log, unified across pipeline stages. */
export interface ProcessingJob {
  id: string;
  kind: ProcessingJobKind;
  status: ProcessingJobStatus;
  sourceId: string;
  sourceName: string;
  sourceItemId: string | null;
  subject: string;
  startedAt: string;
  durationMs: number | null;
  summary: string;
  errorMessage: string | null;
  retryCount: number;
  retryable: boolean;
  ingestionRunId: string | null;
  /** True when created or changed by a demo action. Never set by a real backend. */
  simulated?: boolean;
}

export interface ProcessingBacklog {
  awaitingScreening: number;
  awaitingFullText: number;
  awaitingExtraction: number;
  failedNeedingAttention: number;
}
