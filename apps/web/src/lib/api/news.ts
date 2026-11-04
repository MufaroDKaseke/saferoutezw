import * as mock from "@/lib/mock/queries";
import * as actions from "@/lib/mock/actions";
import type { Paginated, SourceItem, SourceItemDetail } from "@/types";
import { route } from "./client";
import type { ActionResult, NewsQuery } from "./types";

export function listNews(query: NewsQuery): Promise<Paginated<SourceItem>> {
  return route({ endpoint: "GET /api/v1/news", query, mock: () => mock.listNews(query) });
}

export function getNewsItem(id: string): Promise<SourceItemDetail> {
  return route({ endpoint: "GET /api/v1/news/{id}", mock: () => mock.getNews(id) });
}

/** Queue a failed article for another attempt. Never reports success of the retry itself. */
export function retryNewsProcessing(id: string): Promise<ActionResult> {
  return route({ endpoint: "POST /api/v1/news/{id}/retry", mock: () => actions.retryArticle(id) });
}
