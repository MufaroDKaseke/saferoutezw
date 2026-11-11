import type { ArticleState, ReviewStatus } from "./taxonomy";

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
  generated_at: string;
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
