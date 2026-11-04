import type { ReviewState } from "./editorial";
import type {
  EvidenceRole,
  GeoPoint,
  IncidentStatus,
  IncidentType,
  Province,
  ReviewPriority,
  RiskLevel,
  Severity,
} from "./common";

/**
 * Derived verification state. An incident candidate is never "confirmed" by AI
 * or by keyword relevance; only an editor can move it past `single_source`.
 */
export type VerificationState =
  | "unverified"
  | "single_source"
  | "corroborated"
  | "editor_confirmed";

/** Mirrors `incident_evidence`: links an incident to a source article. */
export interface IncidentEvidence {
  id: string;
  incidentId: string;
  sourceItemId: string;
  role: EvidenceRole;
  articleTitle: string;
  publisherName: string;
  publishedAt: string | null;
  canonicalUrl: string | null;
  /** Evidence snippet taken from the article, already privacy-redacted. */
  snippet: string | null;
  extractionRunId: string | null;
  extractedEventId: string | null;
}

/** Historical risk context. Proximity to a blackspot is NOT evidence an incident happened. */
export interface IncidentBlackspotMatch {
  blackspotId: string;
  code: string;
  name: string;
  distanceKm: number;
}

/** Mirrors `incidents`, with response-only convenience fields. */
export interface Incident {
  id: string;
  referenceCode: string;
  title: string;
  incidentType: IncidentType;
  severity: Severity;
  locationText: string | null;
  roadName: string | null;
  province: Province | null;
  point: GeoPoint | null;
  occurredAt: string | null;
  /** Shown when the time is unknown or only approximate. */
  occurredAtNote: string | null;
  /** 0..1 decision aid for editors. Never a verdict. */
  credibilityScore: number | null;
  credibilityRationale: string | null;
  /** 0..1 historical-risk context. Separate from credibility. */
  geographicRiskScore: number | null;
  riskLevel: RiskLevel | null;
  reviewPriority: ReviewPriority;
  status: IncidentStatus;
  /** Derived from `status` and the latest human decision. */
  reviewState: ReviewState;
  verification: VerificationState;
  /** Internal, AI-drafted summary. Not public text. */
  summary: string;
  vehicles: string[];
  trafficImpact: string | null;
  missingInformation: string[];
  sourceCount: number;
  createdAt: string;
  updatedAt: string;
  synthetic?: boolean;
}

/** How firmly an incident's position is known (API mode). Mirrors LocationOut. */
export interface LocationInfo {
  status: "unresolved" | "ambiguous" | "resolved" | "editor_confirmed";
  source: string | null;
  method: string | null;
  precisionMeters: number | null;
  note: string | null;
  confirmedByEditor: boolean;
  /** Alternatives from the geographic reference. Never drawn as markers. */
  candidates: { label: string; latitude: number; longitude: number; precisionMeters: number | null; source: string }[];
}

export interface IncidentDetail extends Incident {
  /** Present in API mode only. */
  locationInfo?: LocationInfo;
  evidence: IncidentEvidence[];
  blackspotMatches: IncidentBlackspotMatch[];
  extractionConfidence: number | null;
  extractionModel: string | null;
}

export interface Blackspot {
  id: string;
  /** Short reference, e.g. D-01. */
  code: string;
  name: string;
  roadName: string | null;
  province: Province | null;
  riskLevel: RiskLevel;
  point: GeoPoint;
  radiusKm: number;
  observationPeriod: { from: string | null; to: string | null };
  dataSourceName: string;
  sourceReference: string;
  /** True for every fixture. Synthetic blackspots are not official records. */
  synthetic: boolean;
  nearbyIncidentCount: number;
  notes: string | null;
}
