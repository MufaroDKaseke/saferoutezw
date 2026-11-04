import type { IngestionRun, SourceItem, SourceSummary } from "./ingestion";
import type { Incident } from "./incidents";
import type { ReviewQueueItem } from "./editorial";

export type DashboardRange = "24h" | "7d" | "30d";

export interface DashboardKpis {
  articlesIngested: number;
  roadRelevantArticles: number;
  incidentCandidates: number;
  pendingReviews: number;
  highPriorityPending: number;
  oldestPendingDays: number | null;
  approvedAlerts: number;
  failedJobs: number;
}

/** "How a report becomes an alert": each step is a separate count, never one blended number. */
export interface DashboardPipeline {
  ingested: number;
  /** AI extraction finished. Suggestions only. */
  aiExtracted: number;
  awaitingDecision: number;
  approvedByEditor: number;
  /** Published with no failed channel. */
  fullyShared: number;
}

export interface ActivityPoint {
  /** ISO date (day). */
  date: string;
  articles: number;
  relevant: number;
  candidates: number;
}

export interface DashboardSummary {
  range: DashboardRange;
  /** When the figures were computed. In mock mode this is the fixed demo snapshot time. */
  asOf: string;
  kpis: DashboardKpis;
  pipeline: DashboardPipeline;
  activity: ActivityPoint[];
  recentNews: SourceItem[];
  queue: ReviewQueueItem[];
  sourceHealth: SourceSummary[];
  lastRuns: IngestionRun[];
  /** Incidents with usable coordinates only. */
  mapIncidents: Incident[];
}
