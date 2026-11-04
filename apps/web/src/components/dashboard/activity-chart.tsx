"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatDay, formatTime } from "@/lib/formatters/date";
import type { ActivityPoint, DashboardRange } from "@/types";

const SERIES = [
  { key: "articles", name: "Articles ingested", color: "#cbd5e1" },
  { key: "relevant", name: "Road-relevant", color: "#334155" },
  { key: "candidates", name: "Incident candidates (AI-extracted)", color: "#6366f1" },
] as const;

export function ActivityChart({ data, range }: { data: ActivityPoint[]; range: DashboardRange }) {
  const label = (iso: string) => (range === "24h" ? formatTime(iso) : formatDay(iso));
  const rows = data.map((d) => ({ ...d, label: label(d.date) }));
  const total = data.reduce((s, d) => s + d.articles + d.candidates, 0);

  if (total === 0) {
    return <p className="py-10 text-center text-sm text-slate-600">No activity in this period.</p>;
  }

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-80 w-full flex-1" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 8, left: -16, bottom: 0 }} barGap={2}>
            <CartesianGrid vertical={false} stroke="#e2e8f0" />
            <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#64748b" }} interval="preserveStartEnd" />
            <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#64748b" }} />
            <Tooltip
              cursor={{ fill: "#f1f5f9" }}
              contentStyle={{ borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 12, boxShadow: "0 4px 12px rgba(15,23,42,.08)" }}
            />
            <Legend
              iconType="circle"
              wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
              formatter={(value: string) => <span style={{ color: "#334155" }}>{value}</span>}
            />
            {SERIES.map((s) => (
              <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} radius={[3, 3, 0, 0]} maxBarSize={22} isAnimationActive={false} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      {/* The chart is visual only; this table carries the same numbers for screen readers. */}
      <table className="sr-only">
        <caption>Articles and incident candidates by {range === "24h" ? "3-hour period" : "day"}</caption>
        <thead>
          <tr>
            <th>Period</th>
            {SERIES.map((s) => (
              <th key={s.key}>{s.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.date}>
              <td>{r.label}</td>
              <td>{r.articles}</td>
              <td>{r.relevant}</td>
              <td>{r.candidates}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
