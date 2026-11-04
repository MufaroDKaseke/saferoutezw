"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Chip } from "@/components/shared/status";
import type { IntelligenceStatistics, ObservationOut } from "@/lib/api/intelligence";
import { formatFigure, formatPeriod } from "@/lib/domain/intelligence";

type Series = IntelligenceStatistics["series"][number];

const VERIFICATION_LABEL: Record<string, string> = {
  verified: "Verified by an editor",
  unverified: "Not yet verified",
  rejected: "Rejected",
};

/** Points of one series keyed by their reporting period. Different sources never share a bar. */
export function seriesRows(points: ObservationOut[]) {
  return points.map((p) => ({
    id: p.id,
    period: formatPeriod(p.period_start, p.period_end),
    value: p.value,
    source: p.source_reference ?? "Source not stated",
    preliminary: p.is_preliminary === true,
    verification: p.verification_status,
  }));
}

export function StatisticsSeriesCard({ series }: { series: Series }) {
  const rows = seriesRows(series.points);
  const sources = Array.from(new Set(rows.map((r) => r.source)));
  const mixedSources = sources.length > 1;
  return (
    <section className="rounded-xl border bg-card p-4" aria-label={`${series.metric} (${series.unit})`}>
      <h3 className="text-sm font-bold">
        {series.metric} <span className="font-normal text-slate-600">({series.unit})</span>
      </h3>
      <p className="text-xs text-slate-600">Coverage: {series.geographic_coverage ?? "not stated"}</p>
      {mixedSources ? (
        <p role="note" className="mt-2 rounded-md bg-amber-50 px-2.5 py-1.5 text-xs text-amber-950">
          These figures come from different sources ({sources.join("; ")}). Compare them with care: definitions may differ.
        </p>
      ) : null}
      {rows.length > 1 ? (
        <div className="mt-3 h-52 w-full" aria-hidden>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="period" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#64748b" }} />
              <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#64748b" }} />
              <Tooltip cursor={{ fill: "#f1f5f9" }} contentStyle={{ borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 12 }} />
              <Bar dataKey="value" name={series.metric} fill="#334155" radius={[3, 3, 0, 0]} maxBarSize={36} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : null}
      <table className="mt-3 w-full text-sm">
        <caption className="sr-only">
          {series.metric} by reporting period, with source and verification
        </caption>
        <thead className="text-left text-xs text-slate-600">
          <tr>
            <th className="py-1 pr-3">Reporting period</th>
            <th className="pr-3">Figure</th>
            <th className="pr-3">Source</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t">
              <td className="py-1.5 pr-3">{r.period}</td>
              <td className="tnum pr-3 font-semibold">{formatFigure(r.value, series.unit)}</td>
              <td className="pr-3 text-xs">{r.source}</td>
              <td className="space-x-1">
                <Chip tone={r.verification === "verified" ? "emerald" : "amber"}>{VERIFICATION_LABEL[r.verification] ?? r.verification}</Chip>
                {r.preliminary ? <Chip tone="amber">Preliminary</Chip> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function StatisticsPanel({ data }: { data: IntelligenceStatistics }) {
  if (data.series.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-slate-600">
        No statistical figures have been extracted yet. They appear here when a report with reported figures is classified.
      </p>
    );
  }
  return (
    <div className="space-y-4">
      <p role="note" className="text-xs text-slate-600">
        {data.note}
      </p>
      <div className="grid gap-4 xl:grid-cols-2">
        {data.series.map((s) => (
          <StatisticsSeriesCard key={`${s.metric}|${s.unit}|${s.geographic_coverage}`} series={s} />
        ))}
      </div>
    </div>
  );
}
