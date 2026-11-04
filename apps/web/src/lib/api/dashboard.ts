import * as mock from "@/lib/mock/queries";
import type { DashboardRange, DashboardSummary } from "@/types";
import { route } from "./client";

export function getDashboard(range: DashboardRange): Promise<DashboardSummary> {
  return route({ endpoint: "GET /api/v1/dashboard", query: { range }, mock: () => mock.getDashboard(range) });
}
