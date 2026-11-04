import * as mock from "@/lib/mock/queries";
import * as actions from "@/lib/mock/actions";
import type { Paginated, SourceItem, SourceItemDetail } from "@/types";
import { dual, route } from "./client";
import { getNewsLive, listNewsLive } from "./live/queries";
import type { ActionResult, NewsQuery } from "./types";

export function listNews(query: NewsQuery): Promise<Paginated<SourceItem>> {
  return dual({ mock: () => mock.listNews(query), live: () => listNewsLive(query) });
}

export function getNewsItem(id: string): Promise<SourceItemDetail> {
  return dual({ mock: () => mock.getNews(id), live: () => getNewsLive(id) });
}

/** Queue a failed article for another attempt. Never reports success of the retry itself. */
export function retryNewsProcessing(id: string): Promise<ActionResult> {
  return route({ endpoint: "POST /api/v1/news/{id}/retry", mock: () => actions.retryArticle(id) });
}
