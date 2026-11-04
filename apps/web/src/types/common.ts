/**
 * Shared vocabulary. Every string union below mirrors a StrEnum in
 * apps/api/app/models/enums.py, so values the backend will return later need no
 * translation. Frontend-only derived states live in the domain files and are
 * documented as derived.
 */

export type DataMode = "mock" | "api";

export type SourceKind = "rss" | "official" | "whatsapp" | "social" | "manual";
export type VerificationTier = "official" | "established_media" | "community" | "unverified";
export type IngestionStatus = "running" | "succeeded" | "partial" | "failed";
/**
 * Mirrors ProcessingStatus in apps/api/app/models/enums.py, including the RSS →
 * article → AI pipeline states: pending → filtered | screened → fetch_failed |
 * fetched → processed | discarded | failed.
 */
export type ProcessingStatus =
  | "pending"
  | "processing"
  | "processed"
  | "failed"
  | "discarded"
  | "filtered"
  | "screened"
  | "fetched"
  | "fetch_failed";

export type IncidentType =
  | "collision"
  | "pedestrian_strike"
  | "rollover"
  | "vehicle_fire"
  | "breakdown"
  | "road_hazard"
  | "road_closure"
  | "traffic_disruption"
  | "other";

export type Severity = "unknown" | "minor" | "serious" | "fatal";
export type ReviewPriority = "low" | "normal" | "high" | "urgent";
export type IncidentStatus =
  | "candidate"
  | "under_review"
  | "approved"
  | "rejected"
  | "published"
  | "archived";
export type EvidenceRole = "primary" | "corroborating" | "contradicting" | "context";
export type ExtractionStatus = "pending" | "succeeded" | "failed";
export type RiskLevel = "low" | "medium" | "high" | "critical";
export type UserRole = "admin" | "editor" | "analyst" | "contributor" | "service";
export type ReviewDecision = "approved" | "rejected" | "needs_changes";
export type AlertStatus = "ready" | "published" | "withdrawn";
export type ChannelKind = "web" | "email" | "sms" | "whatsapp" | "webhook";
export type OutboxStatus = "pending" | "sending" | "sent" | "failed" | "cancelled";
export type AttemptStatus = "succeeded" | "failed";

/** A province or metropolitan area used for filtering. */
export type Province =
  | "Harare"
  | "Bulawayo"
  | "Manicaland"
  | "Mashonaland Central"
  | "Mashonaland East"
  | "Mashonaland West"
  | "Masvingo"
  | "Matabeleland North"
  | "Matabeleland South"
  | "Midlands";

/** Roles that may record an editorial decision (mirrors REVIEWER_ROLES). */
export const REVIEWER_ROLES: readonly UserRole[] = ["admin", "editor"];

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface DemoUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  title: string;
  /** Demo sessions are never real authentication. */
  isDemo: true;
}

/** The signed-in person: the demo user in mock mode, a real API session in api mode. */
export interface SessionUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  title: string;
  isDemo: boolean;
}

export interface GeoPoint {
  lat: number;
  lng: number;
  /**
   * How precisely the position is known. Anything coarser than `road_segment`
   * must never be presented as an exact crash site.
   */
  accuracy: "exact" | "road_segment" | "town" | "approximate";
  /** True for every coordinate in the mock dataset. */
  synthetic: boolean;
}
