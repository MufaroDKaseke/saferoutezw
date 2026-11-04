import * as mock from "@/lib/mock/queries";
import type { DashboardRange, DashboardSummary } from "@/types";
import { dual } from "./client";
import { getDashboardLive } from "./live/queries";

export function getDashboard(range: DashboardRange): Promise<DashboardSummary> {
  return dual({ mock: () => mock.getDashboard(range), live: () => getDashboardLive(range) });
}
