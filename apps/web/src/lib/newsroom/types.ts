import type { ArticleState, ReviewStatus, ScriptOrigin, StoryDecision, StoryStage } from "./taxonomy";

/** Shapes returned by `/api/v1/newsroom/*` (see `apps/api/app/schemas/newsroom_api.py`). */

export interface ArticleReview {
  status: ReviewStatus;
  by: string | null;
  at: string | null;
  note: string | null;
}

export interface NewsroomArticle {
  id: string;
  publisher_id: string;
  publisher: string;
  headline: string;
  source_url: string | null;
  published_at: string | null;
  collected_at: string;
  state: ArticleState;
  processing_status: string;
  category: string | null;
  secondary_category: string | null;
  summary: string | null;
  geographic_relevance: string | null;
  needs_editorial_attention: boolean;
  classification_basis: "full_text" | "excerpt" | "headline" | null;
  review: ArticleReview;
}

export interface NewsroomArticleDetail extends NewsroomArticle {
  excerpt: string | null;
  article_text: string | null;
  topics: string[];
  organisations: string[];
  places: string[];
  attention_reason: string | null;
  /** How clearly the text supports the category. Not the probability that the article is true. */
  classification_confidence: number | null;
  model: string | null;
  prompt_version: string | null;
  classified_at: string | null;
  reused_from: string | null;
  fetch_error: string | null;
  last_error: string | null;
  /** The story built from this article, if someone took it. */
  story: StoryLink | null;
}

export interface NewsroomPage {
  items: NewsroomArticle[];
  total: number;
  page: number;
  page_size: number;
}

export interface NewsroomSummary {
  total_articles: number;
  collected_today: number;
  classified_today: number;
  pending_classification: number;
  failures: number;
  feeds: { enabled: number; healthy: number; unhealthy: number; disabled: number };
  usage_today: { input_tokens: number; output_tokens: number; estimated_cost_usd: number | null };
  by_category: { key: string; label: string; count: number }[];
  publishers: { id: string; name: string; articles: number; classified: number }[];
  workflow: WorkflowSummary;
  generated_at: string;
}

/* ------------------------------------------------------------------ story-to-air workflow */
/** Shapes returned by `/api/v1/newsroom/stories` (see `apps/api/app/schemas/newsroom_workflow.py`). */

export interface Person {
  id: string;
  display_name: string;
}

export interface Assignee extends Person {
  role: string;
}

export interface StoryLink {
  id: string;
  title: string;
  stage: StoryStage;
  assignee: Person;
}

export interface StorySummary {
  id: string;
  title: string;
  stage: StoryStage;
  assignee: Person;
  deadline_at: string | null;
  source_item_id: string | null;
  article_headline: string | null;
  verified: boolean;
  latest_script_version: number | null;
  /** Estimated reading time of the newest script, in seconds. */
  latest_script_seconds: number | null;
  /** The script version a person approved, if any. */
  approved_script_version: number | null;
  follows_story_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface StoryScript {
  id: string;
  version_number: number;
  headline: string;
  body: string;
  estimated_seconds: number;
  origin: ScriptOrigin;
  model_name: string | null;
  prompt_version: string | null;
  created_by: Person;
  created_at: string;
}

export interface StoryReview {
  id: string;
  script_id: string;
  script_version: number;
  decision: StoryDecision;
  comment: string | null;
  self_approved: boolean;
  reviewer: Person;
  reviewed_at: string;
}

export interface StoryDetail extends StorySummary {
  verification: { note: string; at: string; by: Person } | null;
  article: { id: string; headline: string; publisher: string; source_url: string | null; published_at: string | null } | null;
  scripts: StoryScript[];
  reviews: StoryReview[];
  /** Words per minute behind every reading-time estimate. */
  reading_wpm: number;
}

export interface StoryPage {
  items: StorySummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface StoryQuery {
  page?: number;
  pageSize?: number;
  stage?: readonly StoryStage[];
  assigneeId?: string;
  q?: string;
}

export interface TakeStoryInput {
  sourceItemId?: string;
  title?: string;
  assigneeId?: string;
  deadlineAt?: string | null;
  /** The earlier story this one follows up. */
  followsStoryId?: string;
}

/* ------------------------------------------------------------------ radio bulletins */
/** Shapes returned by `/api/v1/newsroom/bulletins` (see `apps/api/app/schemas/newsroom_workflow.py`). */

export type RevisionState = "draft" | "pending_approval" | "approved" | "superseded" | "rejected";

export interface BulletinItem {
  position: number;
  story: { id: string; title: string; stage: StoryStage };
  script: { id: string; version_number: number; headline: string; estimated_seconds: number };
  /** The pinned script version carries an approving review. */
  script_approved: boolean;
  /** The story has been rewritten since this version was pinned. Only a flag: the pinned version is what is read. */
  newer_script_version: number | null;
  /** The override for a clip, otherwise the script's reading-time estimate. */
  duration_seconds: number;
  duration_overridden: boolean;
  note: string | null;
}

export interface BulletinDecision {
  decision: "approved" | "rejected";
  comment: string | null;
  self_approved: boolean;
  reviewer: Person;
  decided_at: string;
}

export interface BulletinRevision {
  id: string;
  revision_number: number;
  state: RevisionState;
  items: BulletinItem[];
  total_seconds: number;
  created_by: Person;
  created_at: string;
  submitted_by: Person | null;
  submitted_at: string | null;
  approved_by: Person | null;
  approved_at: string | null;
  aired_by: Person | null;
  aired_at: string | null;
  decisions: BulletinDecision[];
}

export interface BulletinSummary {
  id: string;
  name: string;
  scheduled_for: string;
  target_seconds: number;
  approved_revision_number: number | null;
  approved_at: string | null;
  approved_total_seconds: number | null;
  latest_revision_number: number;
  latest_revision_state: RevisionState;
  aired_at: string | null;
  created_by: Person;
  created_at: string;
}

export interface BulletinDetail extends BulletinSummary {
  revisions: BulletinRevision[];
}

export interface BulletinPage {
  items: BulletinSummary[];
  total: number;
  page: number;
  page_size: number;
}

/** One row of the running order as the builder edits it. `scriptId: null` lets the server pick the script. */
export interface BulletinItemDraft {
  storyId: string;
  scriptId: string | null;
  durationOverrideSeconds: number | null;
  note: string;
}

/* ------------------------------------------------------------------ studio view */

export interface StudioItem {
  position: number;
  story_title: string;
  headline: string;
  body: string;
  duration_seconds: number;
  duration_overridden: boolean;
  note: string | null;
}

/** The server's one answer for the studio screen. Always read fresh; never remembered by the browser. */
export interface StudioView {
  bulletin_id: string;
  name: string;
  scheduled_for: string;
  target_seconds: number;
  status: "approved" | "not_approved";
  /** The approved revision number: the version to read. */
  version: number | null;
  approved_at: string | null;
  approved_by: Person | null;
  items: StudioItem[];
  total_seconds: number;
  /** A newer revision awaits approval. The version above is still the live one. */
  newer_revision_pending: boolean;
  newer_revision_number: number | null;
  aired_at: string | null;
  server_time: string;
}

/* ------------------------------------------------------------------ archive and dashboard */
/** Shapes returned by `/api/v1/newsroom/archive` (see `apps/api/app/schemas/newsroom_workflow.py`). */

export interface ArchiveBulletinRef {
  id: string;
  name: string;
  revision_number: number;
  aired_at: string;
}

export interface ArchiveStoryLink {
  id: string;
  title: string;
  aired_at: string;
}

export interface ArchiveStory {
  id: string;
  title: string;
  /** The headline of the script version that went to air. */
  headline: string;
  excerpt: string;
  category: string | null;
  category_label: string | null;
  /** When it first went to air. */
  aired_at: string;
  last_aired_at: string;
  bulletins: ArchiveBulletinRef[];
  reporter: Person;
  follows: ArchiveStoryLink | null;
  follow_up_count: number;
  publisher: string | null;
  source_url: string | null;
}

export interface ArchiveScript {
  version_number: number;
  headline: string;
  body: string;
  estimated_seconds: number;
  origin: ScriptOrigin;
  created_by: Person;
  created_at: string;
  aired_in: ArchiveBulletinRef[];
}

export interface ArchiveVersion {
  version_number: number;
  origin: ScriptOrigin;
  created_by: Person;
  created_at: string;
  approved: boolean;
  aired: boolean;
}

export interface ArchiveReview {
  script_version: number;
  decision: StoryDecision;
  comment: string | null;
  self_approved: boolean;
  reviewer: Person;
  reviewed_at: string;
}

export interface ArchiveStoryDetail extends ArchiveStory {
  source_item_id: string | null;
  /** Every script version that went to air, with its text. */
  scripts: ArchiveScript[];
  /** The whole version history. Only aired versions carry text, in `scripts`. */
  versions: ArchiveVersion[];
  reviews: ArchiveReview[];
  followed_by: ArchiveStoryLink[];
}

export interface ArchiveBulletin {
  id: string;
  name: string;
  scheduled_for: string;
  revision_number: number;
  aired_at: string;
  aired_by: Person;
  total_seconds: number;
  story_count: number;
}

export interface ArchiveBulletinItem extends StudioItem {
  story_id: string;
}

export interface ArchiveBulletinDetail extends ArchiveBulletin {
  target_seconds: number;
  approved_at: string | null;
  approved_by: Person | null;
  items: ArchiveBulletinItem[];
}

export interface ArchivePage<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ArchiveQuery {
  page?: number;
  pageSize?: number;
  q?: string;
  airedFrom?: string;
  airedTo?: string;
  category?: string;
}

/** The dashboard's story-to-air counters. */
export interface WorkflowSummary {
  stories_awaiting_approval: number;
  /** Stories that are neither broadcast nor dropped. */
  stories_in_progress: number;
  bulletins_awaiting_approval: number;
  /** The soonest bulletin that has not gone to air yet. */
  next_bulletin: BulletinSummary | null;
}

export interface NewsroomQuery {
  page?: number;
  pageSize?: number;
  q?: string;
  publisherId?: string;
  category?: string;
  state?: ArticleState;
  reviewStatus?: ReviewStatus;
  publishedFrom?: string;
  collectedFrom?: string;
  sort?: "collected_at" | "published_at";
  order?: "asc" | "desc";
}
