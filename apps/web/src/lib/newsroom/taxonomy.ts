/**
 * The NUST FM newsroom's general news categories and their labels.
 *
 * Kept apart from `lib/taxonomy.generated.ts`, which is generated from the road-safety taxonomy.
 * The values mirror `NewsCategory` in `apps/api/app/schemas/newsroom.py`.
 */

export const NEWS_CATEGORIES = [
  "politics_governance",
  "business_economy",
  "education",
  "health",
  "technology",
  "sports",
  "entertainment_culture",
  "crime_courts",
  "transport_infrastructure",
  "environment_agriculture",
  "community_local",
  "international",
  "other",
] as const;

export type NewsCategory = (typeof NEWS_CATEGORIES)[number];

export const NEWS_CATEGORY_LABEL: Record<NewsCategory, string> = {
  politics_governance: "Politics & Governance",
  business_economy: "Business & Economy",
  education: "Education",
  health: "Health",
  technology: "Technology",
  sports: "Sports",
  entertainment_culture: "Entertainment & Culture",
  crime_courts: "Crime & Courts",
  transport_infrastructure: "Transport & Infrastructure",
  environment_agriculture: "Environment & Agriculture",
  community_local: "Community & Local News",
  international: "International News",
  other: "Other / Unclassified",
};

export const NEWS_CATEGORY_OPTIONS = NEWS_CATEGORIES.map((value) => ({ value, label: NEWS_CATEGORY_LABEL[value] }));

/** Unknown values (for example from a newer backend) fall back to the raw text. */
export function newsCategoryLabel(value: string | null | undefined): string {
  if (!value) return "Not classified";
  return (NEWS_CATEGORY_LABEL as Record<string, string>)[value] ?? value;
}

export const GEOGRAPHIC_LABEL: Record<string, string> = {
  bulawayo: "Bulawayo",
  matabeleland: "Matabeleland",
  zimbabwe_wide: "Zimbabwe-wide",
  international: "International",
  unclear: "Unclear",
};

export const geographicLabel = (value: string | null | undefined): string =>
  value ? (GEOGRAPHIC_LABEL[value] ?? value) : "Unclear";

export const ARTICLE_STATES = ["classified", "pending", "failed", "skipped"] as const;
export type ArticleState = (typeof ARTICLE_STATES)[number];

export const ARTICLE_STATE_OPTIONS: { value: ArticleState; label: string }[] = [
  { value: "classified", label: "Classified" },
  { value: "pending", label: "Waiting for classification" },
  { value: "failed", label: "Failed" },
  { value: "skipped", label: "Left out by an earlier road screen" },
];

export const REVIEW_STATUSES = ["new", "reviewed", "used", "dismissed"] as const;
export type ReviewStatus = (typeof REVIEW_STATUSES)[number];

export const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  new: "New",
  reviewed: "Reviewed",
  used: "Used",
  dismissed: "Dismissed",
};

export const REVIEW_STATUS_OPTIONS = REVIEW_STATUSES.map((value) => ({ value, label: REVIEW_STATUS_LABEL[value] }));

/* ------------------------------------------------------------------ story-to-air workflow */

/** Mirrors `StoryStage` in `apps/api/app/models/enums.py`. */
export const STORY_STAGES = [
  "assigned",
  "drafting",
  "changes_requested",
  "in_review",
  "approved",
  "broadcast",
  "dropped",
] as const;
export type StoryStage = (typeof STORY_STAGES)[number];

export const STORY_STAGE_LABEL: Record<StoryStage, string> = {
  assigned: "Assigned",
  drafting: "Drafting",
  changes_requested: "Sent back",
  in_review: "Awaiting approval",
  approved: "Approved",
  broadcast: "Broadcast",
  dropped: "Dropped",
};

/** Board columns, left to right. Broadcast and dropped stories leave the board; the archive keeps them. */
export const BOARD_STAGES: readonly StoryStage[] = ["assigned", "drafting", "changes_requested", "in_review", "approved"];

/** Stages in which the script can still change (editing an approved story reopens it as a draft). */
export const SCRIPT_EDITABLE_STAGES: readonly StoryStage[] = ["assigned", "drafting", "changes_requested", "approved"];

/** Stages in which a story can still be dropped. */
export const DROPPABLE_STAGES: readonly StoryStage[] = ["assigned", "drafting", "changes_requested", "in_review", "approved"];

export type ScriptOrigin = "human" | "ai_draft";
export type StoryDecision = "approved" | "changes_requested";
