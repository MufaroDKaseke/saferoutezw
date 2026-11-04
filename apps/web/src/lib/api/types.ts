import type {
  AlertPublicationState,
  ArticleWorkflowState,
  ChannelKind,
  IncidentType,
  Province,
  ProcessingJobKind,
  ProcessingJobStatus,
  ReviewPriority,
  ReviewState,
  RiskLevel,
  Severity,
  VerificationState,
} from "@/types";

export type DateRangeKey = "all" | "24h" | "7d" | "30d";

export interface PageQuery {
  page?: number;
  pageSize?: number;
  sort?: string;
  dir?: "asc" | "desc";
}

export interface NewsQuery extends PageQuery {
  search?: string;
  publisherId?: string;
  relevance?: "relevant" | "not_relevant";
  status?: ArticleWorkflowState;
  range?: DateRangeKey;
  keyword?: string;
}

export interface IncidentQuery extends PageQuery {
  search?: string;
  reviewState?: ReviewState;
  type?: IncidentType;
  province?: Province;
  range?: DateRangeKey;
  severity?: Severity;
  verification?: VerificationState;
}

export interface ReviewQuery extends PageQuery {
  search?: string;
  state?: ReviewState | "open";
  priority?: ReviewPriority;
}

export interface AlertQuery extends PageQuery {
  search?: string;
  state?: AlertPublicationState;
  channel?: ChannelKind;
}

export interface BlackspotQuery extends PageQuery {
  search?: string;
  risk?: RiskLevel;
  province?: Province;
}

export interface ProcessingQuery extends PageQuery {
  search?: string;
  kind?: ProcessingJobKind;
  status?: ProcessingJobStatus;
  sourceId?: string;
  range?: DateRangeKey;
}

export interface MapQuery {
  range?: DateRangeKey;
  severity?: Severity;
  search?: string;
}

/**
 * Result of a mutating action. `simulated` is true for every mock-mode action,
 * so the UI can say plainly that nothing real happened.
 */
export interface ActionResult<T = undefined> {
  simulated: boolean;
  message: string;
  data?: T;
}

export interface HealthStatus {
  status: string;
  service: string;
  version: string;
}

export interface SourceInput {
  name: string;
  feedUrl: string;
  pollIntervalSeconds: number;
  verificationTier: "official" | "established_media" | "community" | "unverified";
  rightsNotes?: string | null;
}

export interface SourceTestResult {
  ok: boolean;
  message: string;
  itemsFound: number | null;
}
