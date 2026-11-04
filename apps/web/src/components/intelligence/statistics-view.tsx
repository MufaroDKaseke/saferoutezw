"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { SectionCard } from "@/components/shared/section-card";
import { SegmentedControl } from "@/components/shared/segmented";
import { CardBodySkeleton, QueryError } from "@/components/shared/states";
import { useResource } from "@/hooks/use-resource";
import {
  getIntelligenceInsights,
  getIntelligenceStatistics,
  getIntelligenceTrends,
} from "@/lib/api/intelligence";
import { categoryLabel } from "@/lib/domain/intelligence";
import { StatisticsPanel } from "./statistics-charts";

const SCOPE = [
  { value: "all", label: "All figures" },
  { value: "verified", label: "Verified only" },
] as const;

export function StatisticsView() {
  const [scope, setScope] = useState<"all" | "verified">("all");
  const stats = useResource(`intelligence:stats:${scope}`, () => getIntelligenceStatistics({ verifiedOnly: scope === "verified" }));
  const trends = useResource("intelligence:trends", () => getIntelligenceTrends(12));
  const insights = useResource("intelligence:insights", () => getIntelligenceInsights());

  return (
    <div className="space-y-6">
      <PageHeader
        title="Statistics and trends"
        description="Reported road-safety figures by period and source."
        actions={
          <Button asChild variant="outline">
            <Link href="/intelligence">Back to records</Link>
          </Button>
        }
      />

      <SectionCard
        title="Reported figures"
        description="One chart per metric, unit and coverage. Each bar is one reporting period."
        action={<SegmentedControl label="Which figures" value={scope} onChange={setScope} options={SCOPE} />}
      >
        {stats.error ? <QueryError error={stats.error} onRetry={stats.refetch} /> : stats.data ? <StatisticsPanel data={stats.data} /> : <CardBodySkeleton lines={6} />}
      </SectionCard>

      <SectionCard title="What is being reported" description="Records classified per month. This is a count of reports, not of real-world events.">
        {trends.error ? (
          <QueryError error={trends.error} onRetry={trends.refetch} />
        ) : trends.data ? (
          <div className="space-y-3">
            <p role="note" className="text-xs text-slate-600">{trends.data.caveat}</p>
            {!trends.data.sufficient_data ? (
              <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-950">
                Only {trends.data.total} record{trends.data.total === 1 ? "" : "s"} so far. That is too few to say anything about a trend.
              </p>
            ) : null}
            {trends.data.points.length === 0 ? (
              <p className="text-sm text-slate-600">No records in this period.</p>
            ) : (
              <table className="w-full text-sm">
                <caption className="sr-only">Classified records per month and category</caption>
                <thead className="text-left text-xs text-slate-600">
                  <tr><th className="py-1 pr-3">Month</th><th className="pr-3">Category</th><th>Records</th></tr>
                </thead>
                <tbody>
                  {trends.data.points.map((p) => (
                    <tr key={`${p.month}${p.category}`} className="border-t">
                      <td className="py-1.5 pr-3">{p.month}</td>
                      <td className="pr-3">{categoryLabel(p.category)}</td>
                      <td className="tnum font-semibold">{p.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ) : (
          <CardBodySkeleton lines={4} />
        )}
      </SectionCard>

      <SectionCard title="Leads for editors" description="Related coverage and concentrations. Verify against the sources before reporting.">
        {insights.error ? (
          <QueryError error={insights.error} onRetry={insights.refetch} />
        ) : insights.data ? (
          <div className="space-y-4 text-sm">
            <p role="note" className="text-xs text-slate-600">{insights.data.caveat}</p>
            {insights.data.topic_groups.length === 0 && insights.data.corridors.length === 0 ? (
              <p className="text-slate-600">No related coverage or corridor concentrations yet.</p>
            ) : null}
            {insights.data.topic_groups.map((g) => (
              <div key={g.topic_key} className="rounded-lg border p-3">
                <p className="font-semibold">
                  {categoryLabel(g.category)}: {g.record_count} records from {g.publisher_count} publisher{g.publisher_count === 1 ? "" : "s"}
                </p>
                <p className="text-xs text-slate-600">Copies of one press release are not independent confirmation.</p>
                <ul className="mt-1 list-disc pl-5 text-xs">{g.headlines.map((h) => <li key={h}>{h}</li>)}</ul>
              </div>
            ))}
            {insights.data.corridors.length > 0 ? (
              <ul className="list-disc pl-5 text-xs">
                {insights.data.corridors.map((c) => (
                  <li key={`${c.road_name}${c.category}`}>{c.road_name}: {c.count} {categoryLabel(c.category).toLowerCase()} records</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : (
          <CardBodySkeleton lines={4} />
        )}
      </SectionCard>
    </div>
  );
}
