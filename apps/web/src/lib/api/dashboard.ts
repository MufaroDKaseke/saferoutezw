import * as mock from "@/lib/mock/queries";
import { getDb } from "@/lib/mock/store";
import type { DashboardRange, DashboardSummary, MonthlyIncidents } from "@/types";
import type { components } from "./schema";
import { apiRequest, dual } from "./client";
import { getDashboardLive } from "./live/queries";

export function getDashboard(range: DashboardRange): Promise<DashboardSummary> {
  return dual({ mock: () => mock.getDashboard(range), live: () => getDashboardLive(range) });
}

/** Road incidents per month by severity. Rejected reports are excluded. */
export function getIncidentsByMonth(months = 6): Promise<MonthlyIncidents> {
  return dual({
    mock: () => mockIncidentsByMonth(months),
    live: async () => {
      const data = await apiRequest<components["schemas"]["MonthlyIncidents"]>("GET /api/v1/dashboard/incidents-by-month", {
        query: { months },
      });
      return {
        months: data.months,
        total: data.total,
        verifiedTotal: data.verified_total,
        points: data.points.map((p) => ({
          month: p.month_start,
          total: p.total,
          fatal: p.fatal,
          serious: p.serious,
          minor: p.minor,
          unknown: p.unknown,
          verified: p.verified,
        })),
      };
    },
  });
}

function mockIncidentsByMonth(months: number): MonthlyIncidents {
  const incidents = getDb().incidents.filter((i) => i.reviewState !== "rejected");
  const newest = incidents.reduce((max, i) => Math.max(max, Date.parse(i.occurredAt ?? i.createdAt)), 0) || Date.now();
  const end = new Date(newest);
  const points = Array.from({ length: months }, (_, n) => {
    const start = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - (months - 1 - n), 1));
    const next = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1));
    const inMonth = incidents.filter((i) => {
      const t = Date.parse(i.occurredAt ?? i.createdAt);
      return t >= start.getTime() && t < next.getTime();
    });
    const count = (severity: string) => inMonth.filter((i) => i.severity === severity).length;
    return {
      month: start.toISOString(),
      total: inMonth.length,
      fatal: count("fatal"),
      serious: count("serious"),
      minor: count("minor"),
      unknown: count("unknown"),
      verified: inMonth.filter((i) => i.reviewState === "approved").length,
    };
  });
  return {
    months,
    points,
    total: points.reduce((sum, p) => sum + p.total, 0),
    verifiedTotal: points.reduce((sum, p) => sum + p.verified, 0),
  };
}
