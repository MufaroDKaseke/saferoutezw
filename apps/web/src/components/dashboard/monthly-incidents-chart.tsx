"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { MonthlyIncidents } from "@/types";

const SERIES = [
  { key: "fatal", name: "Fatal", color: "#b91c1c" },
  { key: "serious", name: "Serious", color: "#f59e0b" },
  { key: "minor", name: "Minor", color: "#64748b" },
  { key: "unknown", name: "Severity not stated", color: "#cbd5e1" },
] as const;

const monthFmt = new Intl.DateTimeFormat("en-ZW", { month: "short", year: "2-digit", timeZone: "Africa/Harare" });
const monthLongFmt = new Intl.DateTimeFormat("en-ZW", { month: "long", year: "numeric", timeZone: "Africa/Harare" });

export function MonthlyIncidentsChart({ data }: { data: MonthlyIncidents }) {
  const rows = data.points.map((p) => ({
    ...p,
    label: monthFmt.format(new Date(p.month)),
    long: monthLongFmt.format(new Date(p.month)),
  }));

  if (data.total === 0) {
    return <p className="py-10 text-center text-sm text-slate-600">No road incidents were reported in this period.</p>;
  }

  return (
    <div className="flex h-full flex-col">
      <p className="mb-2 text-sm text-slate-700">
        <strong>{data.total}</strong> road incident{data.total === 1 ? "" : "s"} in the last {data.months} months,{" "}
        <strong>{data.verifiedTotal}</strong> verified by an editor.
      </p>
      <div className="min-h-72 w-full flex-1" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="#e2e8f0" />
            <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#64748b" }} />
            <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#64748b" }} />
            <Tooltip
              cursor={{ fill: "#f1f5f9" }}
              labelFormatter={(_, payload) => payload?.[0]?.payload?.long ?? ""}
              contentStyle={{ borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 12, boxShadow: "0 4px 12px rgba(15,23,42,.08)" }}
            />
            <Legend
              iconType="circle"
              wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
              formatter={(value: string) => <span style={{ color: "#334155" }}>{value}</span>}
            />
            {SERIES.map((s, n) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={s.name}
                stackId="incidents"
                fill={s.color}
                radius={n === SERIES.length - 1 ? [3, 3, 0, 0] : 0}
                maxBarSize={44}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
      {/* The chart is visual only; this table carries the same numbers for screen readers. */}
      <table className="sr-only">
        <caption>Road incidents per month by severity</caption>
        <thead>
          <tr>
            <th>Month</th>
            <th>Total</th>
            {SERIES.map((s) => (
              <th key={s.key}>{s.name}</th>
            ))}
            <th>Verified by an editor</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.month}>
              <td>{r.long}</td>
              <td>{r.total}</td>
              <td>{r.fatal}</td>
              <td>{r.serious}</td>
              <td>{r.minor}</td>
              <td>{r.unknown}</td>
              <td>{r.verified}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
