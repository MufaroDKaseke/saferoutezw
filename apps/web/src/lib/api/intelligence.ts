import * as mock from "@/lib/mock/intelligence";
import { apiRequest, route } from "./client";
import { isMockMode } from "./config";
import { ApiError } from "./errors";
import type { components } from "./schema";

type S = components["schemas"];

export type IntelligenceSummary = S["IntelligenceSummary"];
export type IntelligenceDetail = S["IntelligenceDetail"];
export type IntelligencePage = S["Page_IntelligenceSummary_"];
export type IntelligenceCategories = S["CategoriesOut"];
export type IntelligenceOverview = S["OverviewOut"];
export type IntelligenceStatistics = S["StatisticsOut"];
export type IntelligenceTrends = S["TrendsOut"];
export type IntelligenceInsights = S["InsightsOut"];
export type ObservationOut = S["ObservationOut"];
export type VersionCreate = S["VersionCreate"];
export type IntelligenceReviewCreate = S["IntelligenceReviewCreate"];

export interface IntelligenceQuery {
  page?: number;
  pageSize?: number;
  category?: string;
  subtype?: string;
  recordKind?: string;
  status?: string;
  q?: string;
  province?: string;
  minConfidence?: number;
}

export function listIntelligence(q: IntelligenceQuery): Promise<IntelligencePage> {
  return route({
    endpoint: "GET /api/v1/intelligence",
    mock: () => mock.listIntelligenceMock(q),
    query: {
      page: q.page,
      page_size: q.pageSize,
      category: q.category,
      subtype: q.subtype,
      record_kind: q.recordKind,
      status: q.status,
      q: q.q,
      province: q.province,
      min_confidence: q.minConfidence,
    },
  });
}

export function getIntelligence(id: string): Promise<IntelligenceDetail> {
  return route({ endpoint: "GET /api/v1/intelligence/{id}", mock: () => mock.getIntelligenceMock(id), params: { id } });
}

export function getIntelligenceCategories(): Promise<IntelligenceCategories> {
  return route({ endpoint: "GET /api/v1/intelligence/categories", mock: mock.categoriesMock });
}

export function getIntelligenceOverview(): Promise<IntelligenceOverview> {
  return route({ endpoint: "GET /api/v1/intelligence/overview", mock: mock.overviewMock });
}

export function getIntelligenceStatistics(query: { metric?: string; verifiedOnly?: boolean } = {}): Promise<IntelligenceStatistics> {
  return route({
    endpoint: "GET /api/v1/intelligence/statistics",
    mock: mock.statisticsMock,
    query: { metric: query.metric, verified_only: query.verifiedOnly },
  });
}

export function getIntelligenceTrends(months = 12): Promise<IntelligenceTrends> {
  return route({ endpoint: "GET /api/v1/intelligence/trends", mock: mock.trendsMock, query: { months } });
}

export function getIntelligenceInsights(): Promise<IntelligenceInsights> {
  return route({ endpoint: "GET /api/v1/intelligence/insights", mock: mock.insightsMock });
}

/* Editorial actions change real records, so they exist only against the live API. */

function liveOnly<T>(action: string, call: () => Promise<T>): Promise<T> {
  if (isMockMode()) {
    return Promise.reject(
      new ApiError(`${action} needs the live API. Demo mode shows synthetic records and never changes them.`, null),
    );
  }
  return call();
}

export function saveIntelligenceVersion(id: string, body: VersionCreate): Promise<S["VersionOut"]> {
  return liveOnly("Saving a version", () =>
    apiRequest("POST /api/v1/intelligence/{id}/versions", { params: { id }, body }),
  );
}

export function reviewIntelligence(id: string, body: IntelligenceReviewCreate): Promise<IntelligenceDetail> {
  return liveOnly("Recording a decision", () =>
    apiRequest("POST /api/v1/intelligence/{id}/reviews", { params: { id }, body }),
  );
}

export function publishIntelligence(id: string, outputType: S["PublishOutputRequest"]["output_type"]): Promise<IntelligenceDetail> {
  return liveOnly("Publishing", () =>
    apiRequest("POST /api/v1/intelligence/{id}/publish", { params: { id }, body: { output_type: outputType } }),
  );
}

export function withdrawIntelligenceOutput(outputId: string): Promise<S["OutputOut"]> {
  return liveOnly("Withdrawing", () =>
    apiRequest("POST /api/v1/intelligence/outputs/{output_id}/withdraw", { params: { output_id: outputId } }),
  );
}
