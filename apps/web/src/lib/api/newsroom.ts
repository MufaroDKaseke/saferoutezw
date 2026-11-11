import type { NewsroomArticleDetail, NewsroomPage, NewsroomQuery, NewsroomSummary } from "@/lib/newsroom/types";
import type { ReviewStatus } from "@/lib/newsroom/taxonomy";
import { apiRequest } from "./client";

/** NUST FM newsroom API. It only exists when the backend runs with APP_MODE=nust_newsroom. */

export function listNewsroomArticles(q: NewsroomQuery, signal?: AbortSignal): Promise<NewsroomPage> {
  return apiRequest<NewsroomPage>("GET /api/v1/newsroom/articles", {
    signal,
    query: {
      page: q.page,
      page_size: q.pageSize,
      q: q.q,
      publisher_id: q.publisherId,
      category: q.category,
      state: q.state,
      review_status: q.reviewStatus,
      published_from: q.publishedFrom,
      collected_from: q.collectedFrom,
      sort: q.sort,
      order: q.order,
    },
  });
}

export function getNewsroomArticle(id: string): Promise<NewsroomArticleDetail> {
  return apiRequest<NewsroomArticleDetail>("GET /api/v1/newsroom/articles/{id}", { params: { id } });
}

export function getNewsroomSummary(): Promise<NewsroomSummary> {
  return apiRequest<NewsroomSummary>("GET /api/v1/newsroom/summary");
}

export function setArticleReview(id: string, status: ReviewStatus, note?: string): Promise<NewsroomArticleDetail> {
  return apiRequest<NewsroomArticleDetail>("PATCH /api/v1/newsroom/articles/{id}/review", {
    params: { id },
    body: { status, note: note?.trim() || null },
  });
}

export function retryNewsroomArticle(id: string): Promise<NewsroomArticleDetail> {
  return apiRequest<NewsroomArticleDetail>("POST /api/v1/newsroom/articles/{id}/retry", { params: { id } });
}
