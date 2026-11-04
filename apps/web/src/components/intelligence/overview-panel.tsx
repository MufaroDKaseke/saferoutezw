"use client";

import Link from "next/link";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SectionCard } from "@/components/shared/section-card";
import { CardBodySkeleton, QueryError } from "@/components/shared/states";
import { useResource } from "@/hooks/use-resource";
import { getIntelligenceOverview, type IntelligenceOverview } from "@/lib/api/intelligence";
import { OUTPUT_LABEL, formatFigure, formatPeriod } from "@/lib/domain/intelligence";
import type { PublicationOutputType } from "@/lib/taxonomy.generated";
import { CategoryBadge, RecordStatusBadge } from "./badges";

/** Rows for the category chart: only categories that have records, so the axis is never padded with zeros. */
export function categoryChartRows(overview: IntelligenceOverview) {
  return overview.by_category
    .filter((c) => c.total > 0)
    .map((c) => ({ category: c.label, total: c.total, awaiting: c.awaiting_review, published: c.published }));
}

export function IntelligenceOverviewBody({ data }: { data: IntelligenceOverview }) {
  const rows = categoryChartRows(data);
  const published = Object.entries(data.published_by_output);
  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-bold">Records by category</h3>
          {rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-600">No classified records yet.</p>
          ) : (
            <>
              <div className="h-64 w-full" aria-hidden>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 12, left: 24, bottom: 0 }}>
                    <CartesianGrid horizontal={false} stroke="#e2e8f0" />
                    <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#64748b" }} />
                    <YAxis type="category" dataKey="category" width={130} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#334155" }} />
                    <Tooltip cursor={{ fill: "#f1f5f9" }} contentStyle={{ borderRadius: 10, border: "1px solid #e2e8f0", fontSize: 12 }} />
                    <Bar dataKey="total" name="Records" fill="#334155" radius={[0, 3, 3, 0]} maxBarSize={18} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <table className="sr-only">
                <caption>Intelligence records by category</caption>
                <thead><tr><th>Category</th><th>Records</th><th>Awaiting review</th><th>Published</th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.category}><td>{r.category}</td><td>{r.total}</td><td>{r.awaiting}</td><td>{r.published}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          <p className="mt-2 text-xs text-slate-600">
            <strong>{data.awaiting_review}</strong> awaiting a human decision. These are reports classified by AI, not verified totals.
          </p>
        </div>

        <div className="space-y-4">
          <div>
            <h3 className="mb-2 text-sm font-bold">Published to the public site</h3>
            {published.length === 0 ? (
              <p className="text-sm text-slate-600">Nothing is published yet.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {published.map(([type, count]) => (
                  <li key={type}>{OUTPUT_LABEL[type as PublicationOutputType] ?? type}: <strong className="tnum">{count}</strong></li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h3 className="mb-2 text-sm font-bold">Latest reported figures</h3>
            {data.latest_statistics.length === 0 ? (
              <p className="text-sm text-slate-600">No statistical figures yet.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {data.latest_statistics.map((s) => (
                  <li key={s.id}>
                    <strong className="tnum">{formatFigure(s.value, s.unit)}</strong> {s.metric}
                    <span className="block text-xs text-slate-600">
                      {formatPeriod(s.period_start, s.period_end)} · {s.source_reference ?? "source not stated"} ·{" "}
                      {s.verification_status === "verified" ? "verified" : "not yet verified"}{s.is_preliminary ? " · preliminary" : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-bold">Recent transport developments</h3>
        {data.recent.length === 0 ? (
          <p className="text-sm text-slate-600">No records yet.</p>
        ) : (
          <ul className="divide-y">
            {data.recent.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <div className="min-w-0">
                  <Link href={`/intelligence/${r.id}`} className="text-sm font-semibold hover:underline">{r.headline}</Link>
                  <div className="mt-0.5"><CategoryBadge category={r.primary_category} subtype={r.primary_subtype} /></div>
                </div>
                <RecordStatusBadge status={r.status} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export function IntelligenceOverviewPanel() {
  const overview = useResource("intelligence:overview", () => getIntelligenceOverview());
  return (
    <SectionCard
      title="Transport intelligence"
      description="Policy, infrastructure, public transport, freight, safety campaigns and statistics, apart from road incidents"
      action={<Link href="/intelligence" className="font-semibold text-emerald-800 hover:underline">Open all records</Link>}
    >
      {overview.error ? <QueryError error={overview.error} onRetry={overview.refetch} /> : overview.data ? <IntelligenceOverviewBody data={overview.data} /> : <CardBodySkeleton lines={8} />}
    </SectionCard>
  );
}
