import type {
  GeographicScope,
  PrimaryCategory,
  RecordKind,
  RecordStatus,
} from "@/lib/taxonomy.generated";

/** How far an article has got through classification. Separate from the processing status. */
export type ClassificationStatus =
  | "unscreened"
  | "filtered"
  | "awaiting_classification"
  | "classified"
  | "not_relevant"
  | "failed";

/**
 * The transport-intelligence reading of a news item. `candidateCategories` are keyword-screen
 * signals only; `primaryCategory` exists once the AI has classified the article (and is still
 * an unverified candidate until an editor approves it).
 */
export interface NewsClassification {
  status: ClassificationStatus;
  primaryCategory: PrimaryCategory | null;
  primarySubtype: string | null;
  candidateCategories: PrimaryCategory[];
  recordKind: RecordKind | null;
  geographicScope: GeographicScope | null;
  geographicRelevance: string | null;
  editorialStatus: RecordStatus | null;
  intelligenceRecordId: string | null;
  linkedIncidentId: string | null;
}
