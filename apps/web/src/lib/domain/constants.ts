import type { IncidentType, Province, ReviewState, RiskLevel, Severity, VerificationState } from "@/types";
import {
  INCIDENT_TYPE_LABEL,
  REVIEW_STATE_LABEL,
  RISK_LABEL,
  SEVERITY_LABEL,
  VERIFICATION_LABEL,
} from "@/lib/formatters/labels";

export const PROVINCES: Province[] = [
  "Harare",
  "Bulawayo",
  "Manicaland",
  "Mashonaland Central",
  "Mashonaland East",
  "Mashonaland West",
  "Masvingo",
  "Matabeleland North",
  "Matabeleland South",
  "Midlands",
];

const options = <T extends string>(labels: Record<T, string>) =>
  (Object.keys(labels) as T[]).map((value) => ({ value, label: labels[value] }));

export const PROVINCE_OPTIONS = PROVINCES.map((p) => ({ value: p, label: p }));
export const INCIDENT_TYPE_OPTIONS = options<IncidentType>(INCIDENT_TYPE_LABEL);
export const SEVERITY_OPTIONS = options<Severity>(SEVERITY_LABEL);
export const REVIEW_STATE_OPTIONS = options<ReviewState>(REVIEW_STATE_LABEL);
export const VERIFICATION_OPTIONS = options<VerificationState>(VERIFICATION_LABEL);
export const RISK_OPTIONS = options<RiskLevel>(RISK_LABEL);
